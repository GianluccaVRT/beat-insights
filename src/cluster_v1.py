"""Clustering V1 / espaço 'meta' (Fase 3): k-means só com metadados estruturados --
BPM, rating, gênero e MyTag via one-hot. Sem features de áudio (isso é V2/
'meta_audio', via librosa, em cluster_v2.py). Persiste os labels em track_clusters
(cluster_version='v1_structured') para permitir comparação com V2/V3 depois, sem
sobrescrever.

A partir do ADR-001 (docs/decisions/ADR-001-tres-espacos-e-knn.md), a construção da
matriz de features vive em src/features.py (build_meta) -- este módulo é um wrapper
fino em cima dela, mantido pra não quebrar cluster_v2.py/cluster_v3.py/explorer.py/
verify_baseline.py, que importam `cluster_v1.build_features`/`load_data`.

Decisões:
- rating=0 ("sem avaliação") é tratado como ponto real na escala contínua, não como
  valor ausente -- descartar essas ~1068 faixas reduziria demais a base pro estágio V1.
- Só bpm e rating são padronizados (StandardScaler); genre e MyTag já são 0/1 via
  one-hot, então entram na distância euclidiana sem escala adicional.
- k é escolhido por silhouette score numa varredura (ver clustering_common.K_RANGE).
"""

from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans

import features as features_mod
from clustering_common import choose_k, get_engine, persist_clusters, plot_pca

CLUSTER_VERSION = "v1_structured"


def load_data(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    return features_mod.load_tracks(engine), features_mod.load_mytag(engine)


def build_features(tracks: pd.DataFrame, mytag: pd.DataFrame) -> pd.DataFrame:
    return features_mod.build_meta(tracks, mytag)


def summarize(tracks: pd.DataFrame, labels) -> pd.DataFrame:
    df = tracks.set_index("track_id").assign(cluster=labels)
    summary = df.groupby("cluster").agg(
        faixas=("bpm", "size"),
        bpm_medio=("bpm", "mean"),
        rating_medio=("rating", "mean"),
        genero_mais_comum=("genre", lambda s: s.mode().iat[0] if not s.mode().empty else None),
    ).round(1)
    print("\n[summarize] Perfil de cada cluster:")
    print(summary.to_string())
    return summary


def main() -> None:
    engine = get_engine()
    tracks, mytag = load_data(engine)
    print(f"[load_data] {len(tracks)} faixas, {mytag.track_id.nunique()} com MyTag")

    features = build_features(tracks, mytag)
    print(f"[build_features] matriz {features.shape[0]} faixas x {features.shape[1]} features")

    best_k, _ = choose_k(features)
    labels = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(features)

    persist_clusters(engine, CLUSTER_VERSION, features.index, labels)
    summarize(tracks, labels)
    out_path = plot_pca(features, labels, "Clustering V1 (metadados estruturados)", "cluster_v1_pca.png")
    print(f"\n[plot_pca] gráfico salvo em {out_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

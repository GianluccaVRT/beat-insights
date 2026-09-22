"""Clustering V2 / espaço 'meta_audio' (Fase 3): metadados estruturados (mesmas
features do V1/'meta') enriquecidos com features de áudio extraídas via librosa
(src/extract_audio_features.py) -- tempo detectado, spectral centroid, RMS energy,
MFCCs, chroma. Persiste em track_clusters (cluster_version='v2_audio') e compara
contra V1 (cluster_version='v1_structured').

A partir do ADR-001 (docs/decisions/ADR-001-tres-espacos-e-knn.md), a construção da
matriz de features vive em src/features.py (build_meta_audio) -- este módulo é um
wrapper fino em cima dela, mantido pra não quebrar cluster_v3.py/explorer.py/
verify_baseline.py, que importam `cluster_v2.build_features`/`load_audio_features`.

Decisões:
- Restrito às faixas com audio_features já extraído (1648/1649 na biblioteca de
  referência -- 1 arquivo referenciado pelo Rekordbox não existe mais em disco,
  ver log de src/extract_audio_features.py). V1/'meta' não tem essa restrição --
  regra única documentada em src/features.py (excluded_from_audio_spaces).
- Todas as features de áudio são padronizadas (StandardScaler): têm escalas muito
  diferentes entre si (ex.: spectral_centroid_mean na casa de milhares, rms_energy
  entre 0-1) e, diferente de genre/MyTag, não são 0/1 -- sem padronizar, dominariam
  a distância euclidiana.
- Comparação V1 x V2 via Adjusted Rand Index (agnóstico à numeração dos clusters) e
  uma tabela de contingência, restrita à interseção de faixas presentes nas duas
  versões.
"""

from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sqlalchemy import text

import cluster_v1
import features as features_mod
from clustering_common import choose_k, get_engine, persist_clusters, plot_pca

CLUSTER_VERSION = "v2_audio"

AUDIO_COLUMNS = features_mod.AUDIO_COLUMNS


def load_audio_features(engine) -> pd.DataFrame:
    return features_mod.load_audio(engine)


def build_features(tracks: pd.DataFrame, mytag: pd.DataFrame, audio: pd.DataFrame) -> pd.DataFrame:
    return features_mod.build_meta_audio(tracks, mytag, audio)


def compare_with_v1(engine, track_ids: pd.Index, labels_v2) -> None:
    v1 = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = 'v1_structured'"),
        engine,
    ).set_index("track_id")

    common = track_ids.intersection(v1.index)
    v1_labels = v1.loc[common, "cluster_label"]
    v2_labels = pd.Series(labels_v2, index=track_ids).loc[common]

    ari = adjusted_rand_score(v1_labels, v2_labels)
    print(f"\n[compare_with_v1] {len(common)} faixas em comum, Adjusted Rand Index V1 x V2 = {ari:.4f}")
    print("(0 = agrupamentos tão diferentes quanto aleatório, 1 = idênticos)")

    contingency = pd.crosstab(v1_labels.rename("cluster_v1"), v2_labels.rename("cluster_v2"))
    print("\n[compare_with_v1] Tabela de contingência (V1 x V2):")
    print(contingency.to_string())


def main() -> None:
    engine = get_engine()
    tracks, mytag = cluster_v1.load_data(engine)
    audio = load_audio_features(engine)
    print(f"[load_data] {len(tracks)} faixas na base, {len(audio)} com audio_features extraído")

    features = build_features(tracks, mytag, audio)
    print(f"[build_features] matriz {features.shape[0]} faixas x {features.shape[1]} features")

    best_k, _ = choose_k(features)
    labels = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(features)

    persist_clusters(engine, CLUSTER_VERSION, features.index, labels)
    cluster_v1.summarize(tracks[tracks.track_id.isin(features.index)], labels)
    compare_with_v1(engine, features.index, labels)

    out_path = plot_pca(features, labels, "Clustering V2 (metadados + áudio)", "cluster_v2_pca.png")
    print(f"\n[plot_pca] gráfico salvo em {out_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

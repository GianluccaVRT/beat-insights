"""Clustering V3 (Fase 3, diagnóstico): k-means só com features de áudio via
librosa -- sem metadados (BPM, rating, gênero, MyTag) na matriz de features.

Motivação (ver README, "Conclusões e próximos passos de melhoria", item 2): o V1
(só metadados) mede completude de metadado mais que som -- 61% da base cai num
cluster dominado por ausência de rating/MyTag, não por semelhança sonora. O V2
combina metadados + áudio, mas a mesma diluição do one-hot esparso do V1 continua
presente dentro da mesma matriz de distância. V3 isola o sinal de áudio puro pra
responder uma pergunta específica: sem o metadado esparso "atrapalhando", o áudio
sozinho forma clusters mais nítidos (silhouette mais alto) do que V1/V2, ou o
groove/timbre real é inerentemente menos separável em blocos discretos?

Persiste em track_clusters (cluster_version='v3_audio_only') e compara com V1 e V2
via Adjusted Rand Index, sem sobrescrever nenhum dos dois.
"""

from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

import cluster_v1
import cluster_v2
from clustering_common import choose_k, get_engine, persist_clusters, plot_pca

CLUSTER_VERSION = "v3_audio_only"


def build_features(audio: pd.DataFrame) -> pd.DataFrame:
    indexed = audio.set_index("track_id")
    scaled = pd.DataFrame(
        StandardScaler().fit_transform(indexed),
        index=indexed.index,
        columns=indexed.columns,
    )
    return scaled.astype(float)


def compare_with(engine, other_version: str, track_ids: pd.Index, labels) -> None:
    other = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
        engine,
        params={"v": other_version},
    ).set_index("track_id")

    common = track_ids.intersection(other.index)
    other_labels = other.loc[common, "cluster_label"]
    these_labels = pd.Series(labels, index=track_ids).loc[common]

    ari = adjusted_rand_score(other_labels, these_labels)
    print(f"[compare_with] {CLUSTER_VERSION} x {other_version}: {len(common)} faixas em comum, ARI = {ari:.4f}")


def main() -> None:
    engine = get_engine()
    tracks, _mytag = cluster_v1.load_data(engine)
    audio = cluster_v2.load_audio_features(engine)
    print(f"[load_data] {len(audio)} faixas com audio_features extraído")

    features = build_features(audio)
    print(f"[build_features] matriz {features.shape[0]} faixas x {features.shape[1]} features (só áudio, sem metadado)")

    best_k, _ = choose_k(features)
    labels = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(features)

    persist_clusters(engine, CLUSTER_VERSION, features.index, labels)

    # Reindexa tracks pra bater exatamente com a ordem de features.index/labels --
    # audio_features não vem necessariamente na mesma ordem da tabela tracks.
    tracks_ordered = tracks.set_index("track_id").loc[features.index].reset_index()
    cluster_v1.summarize(tracks_ordered, labels)

    print()
    compare_with(engine, "v1_structured", features.index, labels)
    compare_with(engine, "v2_audio", features.index, labels)

    out_path = plot_pca(features, labels, "Clustering V3 (só áudio, sem metadados)", "cluster_v3_pca.png")
    print(f"\n[plot_pca] gráfico salvo em {out_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

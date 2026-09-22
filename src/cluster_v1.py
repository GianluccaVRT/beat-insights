"""Clustering V1 (Fase 3): k-means só com metadados estruturados -- BPM, rating,
gênero e MyTag via one-hot. Sem features de áudio (isso é V2, via librosa, etapa
seguinte). Persiste os labels em track_clusters (cluster_version='v1_structured')
para permitir comparação com V2 depois, sem sobrescrever.

Decisões:
- rating=0 ("sem avaliação") é tratado como ponto real na escala contínua, não como
  valor ausente -- descartar essas ~1068 faixas reduziria demais a base pro estágio V1.
- Só bpm e rating são padronizados (StandardScaler); genre e MyTag já são 0/1 via
  one-hot, então entram na distância euclidiana sem escala adicional.
- k é escolhido por silhouette score numa varredura (ver K_RANGE), não fixado a mão.
"""

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

CLUSTER_VERSION = "v1_structured"
K_RANGE = range(4, 16)
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def get_engine():
    load_dotenv()
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def load_data(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    tracks = pd.read_sql("SELECT track_id, bpm, rating, genre FROM tracks", engine)
    mytag = pd.read_sql(
        """
        SELECT tm.track_id, mv.value_name
        FROM track_mytag tm
        JOIN mytag_values mv ON mv.value_id = tm.value_id
        """,
        engine,
    )
    return tracks, mytag


def build_features(tracks: pd.DataFrame, mytag: pd.DataFrame) -> pd.DataFrame:
    numeric = tracks.set_index("track_id")[["bpm", "rating"]]
    numeric_scaled = pd.DataFrame(
        StandardScaler().fit_transform(numeric),
        index=numeric.index,
        columns=["bpm_scaled", "rating_scaled"],
    )

    genre_onehot = pd.get_dummies(tracks.set_index("track_id")["genre"], prefix="genre")

    mytag_onehot = (
        pd.crosstab(mytag["track_id"], mytag["value_name"])
        .clip(upper=1)
        .reindex(tracks["track_id"], fill_value=0)
    )
    mytag_onehot.columns = [f"tag_{c}" for c in mytag_onehot.columns]

    features = pd.concat([numeric_scaled, genre_onehot, mytag_onehot], axis=1)
    return features.astype(float)


def choose_k(features: pd.DataFrame) -> tuple[int, dict[int, float]]:
    scores = {}
    for k in K_RANGE:
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(features)
        scores[k] = silhouette_score(features, labels)
    best_k = max(scores, key=scores.get)
    print("[choose_k] silhouette por k:")
    for k, s in scores.items():
        flag = "  <-- escolhido" if k == best_k else ""
        print(f"  k={k}: {s:.4f}{flag}")
    return best_k, scores


def persist_clusters(engine, track_ids: pd.Index, labels) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM track_clusters WHERE cluster_version = :v"),
            {"v": CLUSTER_VERSION},
        )
    result = pd.DataFrame({"track_id": track_ids, "cluster_version": CLUSTER_VERSION, "cluster_label": labels})
    result.to_sql("track_clusters", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[persist_clusters] {len(result)} linhas gravadas em track_clusters ({CLUSTER_VERSION})")


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


def plot_pca(features: pd.DataFrame, labels) -> Path:
    coords = PCA(n_components=2, random_state=42).fit_transform(features)
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / "cluster_v1_pca.png"

    fig, ax = plt.subplots(figsize=(9, 7))
    scatter = ax.scatter(coords[:, 0], coords[:, 1], c=labels, cmap="tab20", s=12, alpha=0.8)
    ax.set_title(f"Clustering V1 (metadados estruturados) -- projeção PCA 2D, k={labels.max() + 1}")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    legend = ax.legend(*scatter.legend_elements(), title="Cluster", loc="upper right", fontsize="small")
    ax.add_artist(legend)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main() -> None:
    engine = get_engine()
    tracks, mytag = load_data(engine)
    print(f"[load_data] {len(tracks)} faixas, {mytag.track_id.nunique()} com MyTag")

    features = build_features(tracks, mytag)
    print(f"[build_features] matriz {features.shape[0]} faixas x {features.shape[1]} features")

    best_k, _ = choose_k(features)
    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(features)

    persist_clusters(engine, features.index, labels)
    summarize(tracks, labels)
    out_path = plot_pca(features, labels)
    print(f"\n[plot_pca] gráfico salvo em {out_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

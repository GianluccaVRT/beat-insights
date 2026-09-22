"""Utilitários compartilhados entre cluster_v1.py e cluster_v2.py: conexão com o
banco, escolha de k por silhouette score, persistência em track_clusters e o
gráfico de projeção PCA. Mantido separado pra V1 e V2 não duplicarem a mesma
lógica de seleção/gravação -- só a montagem da matriz de features muda entre eles.
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
from sqlalchemy import create_engine, text

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


def choose_k(features: pd.DataFrame, k_range=K_RANGE) -> tuple[int, dict[int, float]]:
    scores = {}
    for k in k_range:
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(features)
        scores[k] = silhouette_score(features, labels)
    best_k = max(scores, key=scores.get)
    print("[choose_k] silhouette por k:")
    for k, s in scores.items():
        flag = "  <-- escolhido" if k == best_k else ""
        print(f"  k={k}: {s:.4f}{flag}")
    return best_k, scores


def persist_clusters(engine, version: str, track_ids: pd.Index, labels) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM track_clusters WHERE cluster_version = :v"), {"v": version})
    result = pd.DataFrame({"track_id": track_ids, "cluster_version": version, "cluster_label": labels})
    result.to_sql("track_clusters", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[persist_clusters] {len(result)} linhas gravadas em track_clusters ({version})")


def plot_pca(features: pd.DataFrame, labels, title: str, filename: str) -> Path:
    coords = PCA(n_components=2, random_state=42).fit_transform(features)
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / filename

    fig, ax = plt.subplots(figsize=(9, 7))
    scatter = ax.scatter(coords[:, 0], coords[:, 1], c=labels, cmap="tab20", s=12, alpha=0.8)
    ax.set_title(f"{title} -- projeção PCA 2D, k={labels.max() + 1}")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    legend = ax.legend(*scatter.legend_elements(), title="Cluster", loc="upper right", fontsize="small")
    ax.add_artist(legend)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path

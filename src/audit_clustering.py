"""Etapa 1 (fase "3 espaços + k-NN", ver ADR-001): auditoria de clustering nos 3
espaços de features (meta/meta_audio/audio). Pra cada espaço:
  - varredura de k=2..20 (silhouette + inércia), salva curva em CSV + PNG;
  - silhouette por cluster no k escolhido;
  - PCA (3 componentes) com variância explicada e os top-8 loadings por componente;
  - persiste os novos rótulos em track_clusters com versão NOVA (não toca em
    v1_structured/v2_audio/v3_audio_only).
Depois monta a matriz de Adjusted Rand Index entre todos os pares (os 3 espaços
novos + os 3 rótulos históricos) e testa as hipóteses H1-H3 registradas no pedido
desta fase.

Rodar: python src/audit_clustering.py
Saída: results/etapa1_2026-09/
"""

import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_samples, silhouette_score
from sqlalchemy import text

import features as features_mod
from clustering_common import get_engine, persist_clusters

RUN_DIR = Path(__file__).resolve().parent.parent / "results" / "etapa1_2026-09"
K_SWEEP = range(2, 21)
RUN_TAG = "2026-09"

HISTORICAL_VERSIONS = {"meta": "v1_structured", "meta_audio": "v2_audio", "audio": "v3_audio_only"}


def k_sweep(features: pd.DataFrame, k_range=K_SWEEP) -> pd.DataFrame:
    rows = []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(features)
        sil = silhouette_score(features, km.labels_)
        rows.append({"k": k, "silhouette": sil, "inertia": km.inertia_})
    return pd.DataFrame(rows)


def plot_k_sweep(sweep_df: pd.DataFrame, space: str, out_path: Path) -> None:
    fig, (ax_sil, ax_inertia) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    ax_sil.plot(sweep_df["k"], sweep_df["silhouette"], marker="o", color="#2a78d6")
    ax_sil.set_ylabel("silhouette")
    ax_sil.set_title(f"Varredura de k -- espaço '{space}'")
    ax_sil.grid(color="#e1e0d9")

    ax_inertia.plot(sweep_df["k"], sweep_df["inertia"], marker="o", color="#eb6834")
    ax_inertia.set_ylabel("inércia (WCSS)")
    ax_inertia.set_xlabel("k")
    ax_inertia.grid(color="#e1e0d9")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def silhouette_by_cluster(features: pd.DataFrame, labels) -> pd.DataFrame:
    samples = silhouette_samples(features, labels)
    df = pd.DataFrame({"cluster": labels, "silhouette": samples})
    return (
        df.groupby("cluster")["silhouette"]
        .agg(n="size", silhouette_mean="mean", silhouette_min="min", silhouette_max="max")
        .round(4)
        .reset_index()
    )


def pca_loadings(features: pd.DataFrame, n_top: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    pca = PCA(n_components=3, random_state=42).fit(features)
    variance_df = pd.DataFrame(
        {"component": ["PC1", "PC2", "PC3"], "explained_variance_ratio": pca.explained_variance_ratio_.round(4)}
    )

    rows = []
    for i, comp_name in enumerate(["PC1", "PC2", "PC3"]):
        loadings = pd.Series(pca.components_[i], index=features.columns)
        top = loadings.reindex(loadings.abs().sort_values(ascending=False).index).head(n_top)
        for rank, (feat, value) in enumerate(top.items(), start=1):
            rows.append({"component": comp_name, "rank": rank, "feature": feat, "loading": round(float(value), 4)})
    return variance_df, pd.DataFrame(rows)


def audit_space(engine, name: str, features: pd.DataFrame) -> dict:
    print(f"\n=== espaço '{name}' -- {features.shape[0]} faixas x {features.shape[1]} features ===")

    sweep_df = k_sweep(features)
    sweep_df.to_csv(RUN_DIR / f"k_sweep_{name}.csv", index=False)
    plot_k_sweep(sweep_df, name, RUN_DIR / f"k_sweep_{name}.png")

    best_row = sweep_df.loc[sweep_df["silhouette"].idxmax()]
    best_k = int(best_row["k"])
    print(f"[k_sweep] k escolhido = {best_k} (silhouette={best_row['silhouette']:.4f})")

    labels = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(features)

    sil_by_cluster = silhouette_by_cluster(features, labels)
    sil_by_cluster.to_csv(RUN_DIR / f"silhouette_by_cluster_{name}.csv", index=False)

    variance_df, loadings_df = pca_loadings(features)
    loadings_df.to_csv(RUN_DIR / f"pca_loadings_{name}.csv", index=False)

    new_version = f"{name}_k{best_k}_{RUN_TAG}"
    persist_clusters(engine, new_version, features.index, labels)

    return {
        "space": name,
        "best_k": best_k,
        "silhouette": float(best_row["silhouette"]),
        "n_features": features.shape[1],
        "n_faixas": features.shape[0],
        "cluster_version": new_version,
        "labels": pd.Series(labels, index=features.index),
        "variance_df": variance_df,
    }


def load_all_labels(engine, versions: list[str]) -> dict[str, pd.Series]:
    out = {}
    for v in versions:
        s = pd.read_sql(
            text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
            engine,
            params={"v": v},
        ).set_index("track_id")["cluster_label"]
        out[v] = s
    return out


def build_ari_matrix(label_sets: dict[str, pd.Series]) -> pd.DataFrame:
    versions = list(label_sets)
    rows = []
    for i, va in enumerate(versions):
        for vb in versions[i + 1 :]:
            la, lb = label_sets[va], label_sets[vb]
            common = la.index.intersection(lb.index)
            ari = adjusted_rand_score(la.loc[common], lb.loc[common])
            rows.append({"version_a": va, "version_b": vb, "n_common": len(common), "ari": round(float(ari), 4)})
    return pd.DataFrame(rows)


def test_h1(sweep_meta: pd.DataFrame) -> dict:
    row_k2 = sweep_meta.loc[sweep_meta["k"] == 2].iloc[0]
    best_row = sweep_meta.loc[sweep_meta["silhouette"].idxmax()]
    confirmed = int(best_row["k"]) == 2
    return {
        "hipotese": "H1: no espaço meta, k=2 tem o maior silhouette (catalogadas vs não-catalogadas)",
        "resultado": "confirmada" if confirmed else "refutada",
        "silhouette_k2": round(float(row_k2["silhouette"]), 4),
        "melhor_k": int(best_row["k"]),
        "melhor_silhouette": round(float(best_row["silhouette"]), 4),
        "nota": (
            "k=2 é de fato o melhor k da varredura" if confirmed
            else f"o melhor k foi {int(best_row['k'])} (silhouette {best_row['silhouette']:.4f}), não k=2 "
                 f"(silhouette {row_k2['silhouette']:.4f})"
        ),
    }


def test_h2(loadings_meta: pd.DataFrame) -> dict:
    pc1 = loadings_meta[loadings_meta["component"] == "PC1"]
    is_rating_or_tag = pc1["feature"].str.startswith("rating") | pc1["feature"].str.startswith("tag_")
    n_rating_tag = int(is_rating_or_tag.sum())
    dominant_feature = pc1.iloc[0]["feature"]
    confirmed = n_rating_tag >= len(pc1) / 2 or is_rating_or_tag.iloc[0]
    return {
        "hipotese": "H2: o PC1 do espaço meta é dominado por rating e colunas de MyTag",
        "resultado": "confirmada" if confirmed else "refutada",
        "top1_feature_pc1": dominant_feature,
        "n_rating_ou_tag_no_top8": n_rating_tag,
        "top8_pc1": pc1[["rank", "feature", "loading"]].to_dict(orient="records"),
        "nota": (
            f"{n_rating_tag}/8 das maiores cargas do PC1 são rating/MyTag, top1={dominant_feature}"
        ),
    }


def test_h3(engine, tracks: pd.DataFrame, mytag: pd.DataFrame, full_meta_labels: pd.Series, full_best_k: int) -> dict:
    tagged_ids = mytag["track_id"].unique()
    tracks_tagged = tracks[tracks.track_id.isin(tagged_ids)]
    mytag_tagged = mytag[mytag.track_id.isin(tagged_ids)]

    features_subset = features_mod.build_meta(tracks_tagged, mytag_tagged)
    print(f"\n=== H3: espaço 'meta' só nas {len(features_subset)} faixas com MyTag ===")

    sweep_subset = k_sweep(features_subset)
    sweep_subset.to_csv(RUN_DIR / "k_sweep_meta_only_tagged.csv", index=False)
    plot_k_sweep(sweep_subset, "meta_only_tagged", RUN_DIR / "k_sweep_meta_only_tagged.png")

    best_row = sweep_subset.loc[sweep_subset["silhouette"].idxmax()]
    best_k_subset = int(best_row["k"])
    labels_subset = pd.Series(
        KMeans(n_clusters=best_k_subset, random_state=42, n_init=10).fit_predict(features_subset),
        index=features_subset.index,
    )

    # não persiste em track_clusters -- diagnóstico ad-hoc sobre um subconjunto,
    # não um espaço de features novo reutilizável.
    labels_full_restricted = full_meta_labels.loc[features_subset.index]
    ari = adjusted_rand_score(labels_full_restricted, labels_subset)

    confirmed = ari < 0.3  # limiar arbitrário mas documentado: ARI baixo = "muda substancialmente"
    return {
        "hipotese": "H3: rodar meta só nas 333 faixas com MyTag muda substancialmente os clusters",
        "resultado": "confirmada" if confirmed else "refutada",
        "n_faixas_com_tag": len(features_subset),
        "k_full_meta": full_best_k,
        "k_subset": best_k_subset,
        "ari_full_restrito_vs_subset": round(float(ari), 4),
        "limiar_usado": 0.3,
        "nota": (
            f"ARI={ari:.4f} entre os rótulos do meta completo (restritos às faixas com tag) e os do "
            f"meta treinado só nessas faixas -- {'baixo, mudou substancialmente' if confirmed else 'alto, não mudou muito'}"
        ),
    }


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    tracks = features_mod.load_tracks(engine)
    mytag = features_mod.load_mytag(engine)
    audio = features_mod.load_audio(engine)

    excluded = features_mod.excluded_from_audio_spaces(tracks, audio)
    print(f"[regra única áudio] {len(excluded)} faixa(s) excluída(s) de 'meta_audio'/'audio': {list(excluded)}")

    spaces_features = {
        "meta": features_mod.build_meta(tracks, mytag),
        "meta_audio": features_mod.build_meta_audio(tracks, mytag, audio),
        "audio": features_mod.build_audio(audio),
    }

    results = {}
    for name, feats in spaces_features.items():
        results[name] = audit_space(engine, name, feats)

    # PCA variance de todos os espaços num CSV só
    variance_all = pd.concat(
        [r["variance_df"].assign(space=name) for name, r in results.items()], ignore_index=True
    )[["space", "component", "explained_variance_ratio"]]
    variance_all.to_csv(RUN_DIR / "pca_variance.csv", index=False)

    # ARI 3x3 (+ históricos)
    new_labels = {r["cluster_version"]: r["labels"] for r in results.values()}
    historical_labels = load_all_labels(engine, list(HISTORICAL_VERSIONS.values()))
    all_labels = {**new_labels, **historical_labels}
    ari_matrix = build_ari_matrix(all_labels)
    ari_matrix.to_csv(RUN_DIR / "ari_matrix_all.csv", index=False)
    print("\n=== ARI entre todos os pares (3 espaços novos + 3 históricos) ===")
    print(ari_matrix.to_string(index=False))

    # Hipóteses
    sweep_meta = pd.read_csv(RUN_DIR / "k_sweep_meta.csv")
    loadings_meta = pd.read_csv(RUN_DIR / "pca_loadings_meta.csv")
    h1 = test_h1(sweep_meta)
    h2 = test_h2(loadings_meta)
    h3 = test_h3(engine, tracks, mytag, results["meta"]["labels"], results["meta"]["best_k"])

    hypotheses = {"gerado_em": date.today().isoformat(), "hipoteses": [h1, h2, h3]}
    (RUN_DIR / "hypotheses.json").write_text(
        json.dumps(hypotheses, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print("\n=== Hipóteses ===")
    for h in (h1, h2, h3):
        print(f"- {h['hipotese']}")
        print(f"  -> {h['resultado'].upper()}: {h['nota']}")

    summary = {
        "gerado_em": date.today().isoformat(),
        "excluidas_de_audio": [int(t) for t in excluded],
        "espacos": {
            name: {
                "cluster_version": r["cluster_version"],
                "best_k": r["best_k"],
                "silhouette": round(r["silhouette"], 4),
                "n_features": r["n_features"],
                "n_faixas": r["n_faixas"],
            }
            for name, r in results.items()
        },
    }
    (RUN_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[audit_clustering] arquivos gravados em {RUN_DIR.relative_to(Path.cwd())}/")


if __name__ == "__main__":
    main()

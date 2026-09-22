"""Clustering restrito a faixas já classificadas (rating > 0 ou com MyTag),
rodando os mesmos 3 espaços de V1/V2/V3 (src/features.py) só dentro desse
subconjunto.

Pergunta motivadora (ver README, "Resultados obtidos", achado do V1): o
cluster dominante do V1 completo (1007/1649, 61% da base) parece separar mais
por *ausência* de rating/MyTag do que por semelhança sonora real. Removendo
as faixas sem classificação da matriz de distância de vez (em vez de só
escondê-las numa visualização), os clusters restantes ficam mais nítidos
(silhouette mais alto) dentro do subconjunto classificado, ou o mesmo
problema de separabilidade persiste mesmo sem a diluição de "tem vs não tem
metadado"?

"Classificada" usa o mesmo critério de `sql/queries/01_faixas_sem_classificacao.sql`
(lá, a negação: sem rating E sem MyTag) -- rating > 0 OU pelo menos 1 MyTag.

Persiste em track_clusters sob 3 cluster_version novas, sufixo "_classified"
(v1_structured_classified/v2_audio_classified/v3_audio_only_classified) --
não sobrescreve as versões "todas as tracks" (v1_structured/v2_audio/
v3_audio_only), usadas aqui só como comparação via Adjusted Rand Index na
interseção dos dois conjuntos de faixas.

Reaproveita src/features.py (build_meta/build_meta_audio/build_audio) e
src/clustering_common.py (choose_k, persist_clusters, plot_pca) -- mesma
lógica de cluster_v1.py/cluster_v2.py/cluster_v3.py, só filtrando a
população de tracks/audio antes de montar a matriz de cada espaço.
"""

import json
from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sqlalchemy import text

import features as features_mod
from clustering_common import choose_k, get_engine, persist_clusters, plot_pca

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "clustering_classificado_2026-09"

# space -> (cluster_version "todas as tracks", cluster_version "classificadas", rótulo)
SPACES = {
    "meta": ("v1_structured", "v1_structured_classified", "V1 (metadados)"),
    "meta_audio": ("v2_audio", "v2_audio_classified", "V2 (metadados + áudio)"),
    "audio": ("v3_audio_only", "v3_audio_only_classified", "V3 (só áudio)"),
}


def classified_ids(tracks: pd.DataFrame, mytag: pd.DataFrame) -> pd.Index:
    tagged = set(mytag["track_id"])
    return tracks.loc[(tracks["rating"] > 0) | tracks["track_id"].isin(tagged), "track_id"].pipe(pd.Index)


def summarize(tracks: pd.DataFrame, labels) -> pd.DataFrame:
    df = tracks.set_index("track_id").assign(cluster=labels)
    return df.groupby("cluster").agg(
        faixas=("bpm", "size"),
        bpm_medio=("bpm", "mean"),
        rating_medio=("rating", "mean"),
        genero_mais_comum=("genre", lambda s: s.mode().iat[0] if not s.mode().empty else None),
    ).round(1)


def compare_with_full(engine, full_version: str, track_ids: pd.Index, labels) -> tuple[float, int]:
    full = pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
        engine, params={"v": full_version},
    ).set_index("track_id")
    common = track_ids.intersection(full.index)
    full_labels = full.loc[common, "cluster_label"]
    these_labels = pd.Series(labels, index=track_ids).loc[common]
    return float(adjusted_rand_score(full_labels, these_labels)), len(common)


def run_space(engine, space: str, tracks: pd.DataFrame, mytag: pd.DataFrame, audio: pd.DataFrame, ids: pd.Index) -> dict:
    full_version, classified_version, label = SPACES[space]

    scoped_tracks = tracks[tracks.track_id.isin(ids)]
    scoped_audio = audio[audio.track_id.isin(ids)]

    if space == "meta":
        features = features_mod.build_meta(scoped_tracks, mytag)
    elif space == "meta_audio":
        features = features_mod.build_meta_audio(scoped_tracks, mytag, scoped_audio)
    else:
        features = features_mod.build_audio(scoped_audio)

    print(f"\n=== {label} ({space}) -- {features.shape[0]} faixas classificadas x {features.shape[1]} features ===")

    best_k, scores = choose_k(features)
    labels = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(features)

    persist_clusters(engine, classified_version, features.index, labels)
    summary = summarize(tracks[tracks.track_id.isin(features.index)], labels)
    print(summary.to_string())

    ari, n_common = compare_with_full(engine, full_version, features.index, labels)
    print(f"[compare_with_full] {n_common} faixas em comum com '{full_version}', ARI = {ari:.4f}")

    out_path = plot_pca(
        features, labels, f"Clustering {label} -- só faixas classificadas", f"cluster_{space}_classified_pca.png"
    )
    print(f"[plot_pca] gráfico salvo em {out_path.relative_to(Path.cwd())}")

    return {
        "space": space,
        "cluster_version": classified_version,
        "n_tracks": int(features.shape[0]),
        "n_features": int(features.shape[1]),
        "best_k": int(best_k),
        "silhouette_by_k": {str(k): round(float(v), 4) for k, v in scores.items()},
        "silhouette_best": round(float(scores[best_k]), 4),
        "ari_vs_full": round(ari, 4),
        "n_common_with_full": n_common,
        "cluster_summary": json.loads(summary.reset_index().to_json(orient="records")),
    }


def main() -> None:
    engine = get_engine()
    tracks = features_mod.load_tracks(engine)
    mytag = features_mod.load_mytag(engine)
    audio = features_mod.load_audio(engine)

    ids = classified_ids(tracks, mytag)
    print(
        f"[classified_ids] {len(ids)} de {len(tracks)} faixas classificadas "
        f"(rating > 0 ou com MyTag) -- {len(ids) / len(tracks):.1%}"
    )

    results = [run_space(engine, space, tracks, mytag, audio, ids) for space in features_mod.SPACES]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = RESULTS_DIR / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(
            {"n_classified": len(ids), "n_total": len(tracks), "spaces": results},
            f, indent=2, ensure_ascii=False,
        )
    print(f"\n[main] resumo salvo em {summary_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

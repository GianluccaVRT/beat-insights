"""Etapa 3 (fase "3 espaços + k-NN", ADR-001): avaliação quantitativa do k-NN via
precision@10 por co-ocorrência em playlist. Pra cada faixa que está em >=1
playlist, a fração dos 10 vizinhos retornados que compartilham pelo menos uma
playlist com ela.

Compara o sistema real (busca por vizinhança + filtros duros de BPM/Camelot,
mesma lógica de similarity.similar_tracks) contra dois baselines:
  - aleatório puro: 10 faixas sorteadas da base, sem filtro nenhum;
  - "mesmo BPM +- key compatível, ordem aleatória": aplica os MESMOS filtros
    duros do sistema real, mas sorteia a ordem em vez de rankear por
    similaridade -- isola se o embedding agrega algo além do filtro sozinho.
Os dois baselines usam 20 sorteios com seed fixa (base_seed + índice do
sorteio), média por faixa.

Grade: 3 espaços x 2 métricas (cosseno, euclidiana), com ablação com/sem chroma
nos 2 espaços que têm áudio (meta_audio, audio) -- 10 configurações no total.
Baseline calculado 1x por espaço (não depende de métrica/chroma), reaproveitado
entre as configs desse espaço.

Viés conhecido, documentado aqui e no README: as playlists desta biblioteca são,
em boa parte, organizadas por gênero/vibe (ex. "Prog House", "Afro House") -- o
espaço 'meta' inclui gênero diretamente como feature, então é estruturalmente
favorecido por uma métrica que mede "co-ocorrência em playlist", não "soa
parecido" de verdade. Ver README pra números concretos.

Rodar: python src/eval_similarity.py
Saída: results/etapa3_2026-09/knn_eval.csv (+ resumo em stdout)
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

import camelot as camelot_mod
import features as features_mod
from clustering_common import get_engine

RUN_DIR = Path(__file__).resolve().parent.parent / "results" / "etapa3_2026-09"
K = 10
N_DRAWS = 20
BASE_SEED = 42
BPM_TOL = 3
CANDIDATE_POOL = 200


def load_playlist_membership(engine) -> dict[int, set[int]]:
    df = pd.read_sql("SELECT track_id, playlist_id FROM track_playlist", engine)
    return df.groupby("track_id")["playlist_id"].apply(set).to_dict()


def _compatible_keys_safe(key_camelot: str) -> set[str]:
    try:
        return set(camelot_mod.compatible_keys(key_camelot))
    except ValueError:
        return {key_camelot}


def precision_at_k(track_id: int, neighbor_ids: list[int], membership: dict[int, set[int]]) -> float:
    if not neighbor_ids:
        return float("nan")
    ref_pl = membership.get(track_id, set())
    hits = sum(1 for nid in neighbor_ids if ref_pl & membership.get(nid, set()))
    return hits / len(neighbor_ids)


def eval_main_system(features: pd.DataFrame, eval_ids: list[int], display: pd.DataFrame, membership, metric: str) -> list[float]:
    pool = min(CANDIDATE_POOL, len(features) - 1)
    nn = NearestNeighbors(n_neighbors=pool + 1, metric=metric, algorithm="brute").fit(features)
    distances, indices = nn.kneighbors(features.loc[eval_ids])
    id_array = features.index.to_numpy()
    display_idx = display.set_index("track_id")

    precisions = []
    for row_i, track_id in enumerate(eval_ids):
        cand_ids = [c for c in id_array[indices[row_i]] if c != track_id]
        ref_bpm = display_idx.loc[track_id, "bpm"]
        compatible_keys = _compatible_keys_safe(display_idx.loc[track_id, "key_camelot"])

        filtered = []
        for cid in cand_ids:
            crow = display_idx.loc[cid]
            if abs(crow["bpm"] - ref_bpm) > BPM_TOL:
                continue
            if crow["key_camelot"] not in compatible_keys:
                continue
            filtered.append(cid)
            if len(filtered) == K:
                break
        precisions.append(precision_at_k(track_id, filtered, membership))
    return precisions


def eval_random_baseline(universe: np.ndarray, eval_ids: list[int], membership) -> list[float]:
    per_track = {tid: [] for tid in eval_ids}
    for draw in range(N_DRAWS):
        rng = np.random.default_rng(BASE_SEED + draw)
        for track_id in eval_ids:
            candidates = universe[universe != track_id]
            sample = rng.choice(candidates, size=min(K, len(candidates)), replace=False)
            per_track[track_id].append(precision_at_k(track_id, list(sample), membership))
    return [_nanmean_allow_all_nan(v) for v in per_track.values()]


def _nanmean_allow_all_nan(values: list[float]) -> float:
    # Faixas com BPM/key muito raros podem não ter NENHUM candidato dentro da
    # tolerância -- todas as 20 tentativas viram NaN pra essa faixa, e
    # np.nanmean avisa "Mean of empty slice" (comportamento esperado, não bug).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return float(np.nanmean(values))


def eval_bpm_camelot_random_baseline(display: pd.DataFrame, eval_ids: list[int], membership) -> list[float]:
    display_idx = display.set_index("track_id")
    per_track = {tid: [] for tid in eval_ids}
    for track_id in eval_ids:
        ref_bpm = display_idx.loc[track_id, "bpm"]
        compatible_keys = _compatible_keys_safe(display_idx.loc[track_id, "key_camelot"])
        mask = (display_idx["bpm"] - ref_bpm).abs() <= BPM_TOL
        mask &= display_idx["key_camelot"].isin(compatible_keys)
        candidates = display_idx.index[mask].to_numpy()
        candidates = candidates[candidates != track_id]

        for draw in range(N_DRAWS):
            rng = np.random.default_rng(BASE_SEED + draw)
            if len(candidates) == 0:
                per_track[track_id].append(float("nan"))
                continue
            sample = rng.choice(candidates, size=min(K, len(candidates)), replace=False)
            per_track[track_id].append(precision_at_k(track_id, list(sample), membership))
    return [_nanmean_allow_all_nan(v) for v in per_track.values()]


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    tracks = features_mod.load_tracks(engine)
    mytag = features_mod.load_mytag(engine)
    audio = features_mod.load_audio(engine)
    display = pd.read_sql("SELECT track_id, bpm, key_camelot FROM tracks", engine)
    membership = load_playlist_membership(engine)
    print(f"[eval] {len(membership)} faixas em >=1 playlist (universo de avaliação)")

    audio_no_chroma = audio[[c for c in audio.columns if not c.startswith("chroma_")]]

    space_configs = {
        "meta": [("meta", features_mod.build_meta(tracks, mytag), None)],
        "meta_audio": [
            ("meta_audio", features_mod.build_meta_audio(tracks, mytag, audio), "com_chroma"),
            ("meta_audio", features_mod.build_meta_audio(tracks, mytag, audio_no_chroma), "sem_chroma"),
        ],
        "audio": [
            ("audio", features_mod.build_audio(audio), "com_chroma"),
            ("audio", features_mod.build_audio(audio_no_chroma), "sem_chroma"),
        ],
    }

    rows = []
    for space, variants in space_configs.items():
        # universo/baseline calculados 1x por espaço (mesmo índice de faixas em
        # todas as variantes de chroma desse espaço)
        features_ref = variants[0][1]
        eval_ids = [tid for tid in features_ref.index if tid in membership]
        universe = features_ref.index.to_numpy()
        print(f"\n=== espaço '{space}' -- {len(eval_ids)} faixas avaliadas de {len(features_ref)} no espaço ===")

        baseline_random = eval_random_baseline(universe, eval_ids, membership)
        baseline_bpm_camelot = eval_bpm_camelot_random_baseline(display, eval_ids, membership)
        print(f"  baseline aleatório: precision@10 média = {np.nanmean(baseline_random):.4f}")
        print(f"  baseline BPM+Camelot (ordem aleatória): precision@10 média = {np.nanmean(baseline_bpm_camelot):.4f}")

        for _, features, chroma_variant in variants:
            for metric in ("cosine", "euclidean"):
                label = f"{space}" + (f"_{chroma_variant}" if chroma_variant else "")
                print(f"  [{label} / {metric}] rodando sistema real...")
                system_precisions = eval_main_system(features, eval_ids, display, membership, metric)

                rows.append({
                    "space": space,
                    "chroma": chroma_variant or "n/a",
                    "metric": metric,
                    "n_faixas_no_espaco": len(features),
                    "n_faixas_avaliadas": len(eval_ids),
                    "precision_at_10_sistema": round(float(np.nanmean(system_precisions)), 4),
                    "precision_at_10_baseline_aleatorio": round(float(np.nanmean(baseline_random)), 4),
                    "precision_at_10_baseline_bpm_camelot": round(float(np.nanmean(baseline_bpm_camelot)), 4),
                    "n_draws_baseline": N_DRAWS,
                    "seed_base": BASE_SEED,
                })
                print(f"    precision@10 sistema = {rows[-1]['precision_at_10_sistema']:.4f}")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(RUN_DIR / "knn_eval.csv", index=False)

    print("\n=== Resumo ===")
    print(result_df.to_string(index=False))

    (RUN_DIR / "summary.json").write_text(
        json.dumps(
            {
                "n_faixas_em_playlist": len(membership),
                "k": K,
                "n_draws_baseline": N_DRAWS,
                "seed_base": BASE_SEED,
                "bpm_tol": BPM_TOL,
                "candidate_pool": CANDIDATE_POOL,
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n[eval_similarity] gravado em {RUN_DIR.relative_to(Path.cwd())}/")


if __name__ == "__main__":
    main()

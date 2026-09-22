"""Busca de vizinhos mais próximos (k-NN) entre faixas, no espaço de features
escolhido -- 'meta', 'meta_audio' ou 'audio' (ver src/features.py, ADR-001).

Busca exata (sklearn.neighbors.NearestNeighbors, algorithm='brute') -- 1649
faixas não justificam índice aproximado (FAISS, pgvector com HNSW/IVF); ver
docs/decisions/ADR-001-tres-espacos-e-knn.md pra essa decisão registrada. Se o
volume da biblioteca crescer o suficiente, pgvector é a evolução natural.

BPM e key Camelot entram como FILTROS DUROS pós-busca, não como parte da
distância: busca-se um pool maior de candidatos (candidate_pool, padrão 200) e
só depois filtra por tolerância de BPM e/ou compatibilidade Camelot -- assim o
ranking de similaridade nunca é distorcido por essas duas dimensões, que têm
semântica de "compatível/incompatível" binária, não de "mais ou menos parecido".

Limitação conhecida do espaço 'meta': ~80% das faixas (1316/1649) não têm
nenhuma MyTag -- ficam com o mesmo vetor de tags (tudo zero), diferindo só por
bpm/rating/gênero. Pra essas faixas, os "vizinhos mais próximos" em 'meta'
tendem a ficar quase empatados entre si (muitas faixas do mesmo gênero à
mesma distância aproximada), sem separação fina de verdade -- k-NN em 'meta' é
informativo sobretudo pras 333 faixas com MyTag (ver Etapa 1, H3:
results/etapa1_2026-09/hypotheses.json).
"""

import pandas as pd
from sklearn.neighbors import NearestNeighbors

import camelot as camelot_mod
import features as features_mod

DEFAULT_CANDIDATE_POOL = 200


def _track_display_info(engine) -> pd.DataFrame:
    """name/artist/bpm/key_camelot pra exibição e pros filtros duros -- não
    usado na construção do espaço de features nem na distância."""
    return pd.read_sql("SELECT track_id, name, artist, bpm, key_camelot FROM tracks", engine)


def similar_tracks(
    engine,
    track_id: int,
    space: str,
    k: int = 10,
    metric: str = "cosine",
    bpm_tol: float | None = 3,
    camelot: bool = True,
    candidate_pool: int = DEFAULT_CANDIDATE_POOL,
    restrict_ids=None,
) -> dict:
    """Retorna os k vizinhos mais próximos de `track_id` no espaço `space`.

    Filtros duros aplicados DEPOIS da busca por vizinhança, sobre um pool de
    `candidate_pool` candidatos (não sobre a base inteira, pra não custar uma
    varredura completa a cada filtro): `bpm_tol` (diferença absoluta de BPM,
    None desliga) e `camelot` (só key compatível pela roda de Camelot, ver
    src/camelot.py).

    `restrict_ids`, quando informado (iterável de track_id), restringe a
    própria matriz de features a esse subconjunto ANTES da busca -- não é um
    filtro pós-busca. Usado pela aba "Vizinhos" do explorer pra comparar
    resultados só entre faixas já classificadas (rating > 0 ou com MyTag),
    já que nesse caso a vizinhança precisa ser recalculada dentro do
    subconjunto, não apenas escondida depois de calculada com a base inteira.
    """
    if space not in features_mod.SPACES:
        return {"error": f"espaço desconhecido: {space!r} -- use um de {features_mod.SPACES}"}

    tracks = features_mod.load_tracks(engine)
    mytag = features_mod.load_mytag(engine)
    audio = features_mod.load_audio(engine)
    if restrict_ids is not None:
        tracks = tracks[tracks.track_id.isin(restrict_ids)]
        audio = audio[audio.track_id.isin(restrict_ids)]
    features = features_mod.build_space(space, tracks, mytag, audio)

    if track_id not in features.index:
        reason = (
            "faixa sem audio_features extraído (arquivo ausente em disco, ver README)"
            if space in ("meta_audio", "audio")
            else "track_id não encontrado na base"
        )
        if restrict_ids is not None:
            reason += " -- ou fora do subconjunto restrito (restrict_ids)"
        return {"error": f"track_id {track_id} não está no espaço {space!r} -- {reason}"}

    pool = min(candidate_pool, len(features) - 1)
    nn = NearestNeighbors(n_neighbors=pool + 1, metric=metric, algorithm="brute").fit(features)
    distances, indices = nn.kneighbors(features.loc[[track_id]])
    distances, indices = distances[0], indices[0]

    candidates = pd.DataFrame({"track_id": features.index[indices], "distance": distances})
    candidates = candidates[candidates.track_id != track_id]

    display = _track_display_info(engine)
    ref_row = display.set_index("track_id").loc[track_id]
    candidates = candidates.merge(display, on="track_id", how="left")

    if bpm_tol is not None:
        candidates = candidates[(candidates["bpm"] - ref_row["bpm"]).abs() <= bpm_tol]
    if camelot:
        try:
            compatible = set(camelot_mod.compatible_keys(ref_row["key_camelot"]))
        except ValueError as exc:
            return {"error": str(exc)}
        candidates = candidates[candidates["key_camelot"].isin(compatible)]

    candidates = candidates.head(k).copy()
    if metric == "cosine":
        candidates["similarity"] = 1 - candidates["distance"]
    else:
        candidates["similarity"] = 1 / (1 + candidates["distance"])

    if space in ("meta_audio", "audio"):
        audio_indexed = audio.set_index("track_id")
        ref_centroid = audio_indexed.loc[track_id, "spectral_centroid_mean"]
        ref_rms = audio_indexed.loc[track_id, "rms_energy_mean"]
        candidates["delta_spectral_centroid"] = (
            candidates["track_id"].map(audio_indexed["spectral_centroid_mean"]) - ref_centroid
        )
        candidates["delta_rms_energy"] = candidates["track_id"].map(audio_indexed["rms_energy_mean"]) - ref_rms
    else:
        candidates["delta_spectral_centroid"] = None
        candidates["delta_rms_energy"] = None

    result_cols = [
        "track_id", "name", "artist", "similarity", "bpm", "key_camelot",
        "delta_spectral_centroid", "delta_rms_energy",
    ]
    matches = candidates[result_cols].round(
        {"similarity": 4, "delta_spectral_centroid": 2, "delta_rms_energy": 4}
    )

    return {
        "reference": {
            "track_id": int(track_id),
            "name": ref_row["name"],
            "artist": ref_row["artist"],
            "bpm": float(ref_row["bpm"]),
            "key_camelot": ref_row["key_camelot"],
        },
        "space": space,
        "metric": metric,
        "bpm_tol": bpm_tol,
        "camelot_filter": camelot,
        "n_candidate_pool": pool,
        "n_matches": len(matches),
        "matches": matches.to_dict(orient="records"),
    }

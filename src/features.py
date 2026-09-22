"""Módulo único de construção dos 3 espaços de features (ver ADR-001:
docs/decisions/ADR-001-tres-espacos-e-knn.md). Usado pelo clustering
(cluster_v1.py/v2.py/v3.py, agora wrappers finos em cima daqui) e pela busca
k-NN (src/similarity.py). Antes desta fase a lógica estava duplicada entre os
três scripts de cluster -- consolidada aqui pra não repetir.

Espaços (apelido histórico entre parênteses):
  - 'meta'       (V1): BPM, rating, gênero, MyTag one-hot -- 83 features.
  - 'meta_audio' (V2): 'meta' + features de áudio padronizadas -- 111 features.
  - 'audio'      (V3): só features de áudio padronizadas -- 28 features.

Regra única pra faixa sem áudio: 'meta' não depende de áudio, então usa todas as
faixas da tabela `tracks`. 'meta_audio' e 'audio' dependem de `audio_features`,
então ficam restritos à interseção com essa tabela -- 1 faixa (track_id=
210208753, "GUIGO TESSEROLI - Caminho", versão MP3) não tem audio_features
extraído porque o arquivo referenciado pelo Rekordbox não existe mais em disco
(ver src/extract_audio_features.py e README, "Limitações conhecidas"). Fica de
fora de 'meta_audio' e 'audio', presente em 'meta'.
"""

import pandas as pd
from sklearn.preprocessing import StandardScaler

SPACES = ("meta", "meta_audio", "audio")

AUDIO_COLUMNS = (
    ["tempo_detected", "spectral_centroid_mean", "rms_energy_mean"]
    + [f"mfcc_{i:02d}" for i in range(1, 14)]
    + [f"chroma_{i:02d}" for i in range(1, 13)]
)


def load_tracks(engine) -> pd.DataFrame:
    return pd.read_sql("SELECT track_id, bpm, rating, genre FROM tracks", engine)


def load_mytag(engine) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT tm.track_id, mv.value_name
        FROM track_mytag tm
        JOIN mytag_values mv ON mv.value_id = tm.value_id
        """,
        engine,
    )


def load_audio(engine) -> pd.DataFrame:
    cols = ", ".join(AUDIO_COLUMNS)
    return pd.read_sql(f"SELECT track_id, {cols} FROM audio_features", engine)


def excluded_from_audio_spaces(tracks: pd.DataFrame, audio: pd.DataFrame) -> pd.Index:
    """track_ids presentes em `tracks` mas ausentes de `audio_features` -- a
    "regra única" pra faixa sem áudio: excluída de 'meta_audio' e 'audio'."""
    return tracks.loc[~tracks.track_id.isin(audio.track_id), "track_id"].pipe(pd.Index)


def build_meta(tracks: pd.DataFrame, mytag: pd.DataFrame) -> pd.DataFrame:
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


def build_meta_audio(tracks: pd.DataFrame, mytag: pd.DataFrame, audio: pd.DataFrame) -> pd.DataFrame:
    scoped_tracks = tracks[tracks.track_id.isin(audio.track_id)]
    structured = build_meta(scoped_tracks, mytag).loc[scoped_tracks.track_id]

    audio_indexed = audio.set_index("track_id").loc[scoped_tracks.track_id]
    audio_scaled = pd.DataFrame(
        StandardScaler().fit_transform(audio_indexed),
        index=audio_indexed.index,
        columns=[f"audio_{c}" for c in audio_indexed.columns],
    )

    return pd.concat([structured, audio_scaled], axis=1).astype(float)


def build_audio(audio: pd.DataFrame) -> pd.DataFrame:
    indexed = audio.set_index("track_id")
    scaled = pd.DataFrame(
        StandardScaler().fit_transform(indexed),
        index=indexed.index,
        columns=indexed.columns,
    )
    return scaled.astype(float)


def build_space(
    name: str,
    tracks: pd.DataFrame,
    mytag: pd.DataFrame | None = None,
    audio: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if name == "meta":
        return build_meta(tracks, mytag)
    if name == "meta_audio":
        return build_meta_audio(tracks, mytag, audio)
    if name == "audio":
        return build_audio(audio)
    raise ValueError(f"espaço desconhecido: {name!r} -- use um de {SPACES}")

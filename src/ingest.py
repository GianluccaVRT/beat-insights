"""Ingestão do CSV "30000 Spotify Songs" para o schema normalizado em PostgreSQL.

Um único script (não dividido em etapas): é um pipeline ETL linear de execução única
sobre um CSV estático, sem necessidade de agendamento ou reuso independente de partes --
dividir em múltiplos arquivos só adicionaria indireção sem ganho nesse escopo.

Decisões de tratamento de dado (números e motivação completos em docs/spec.md):
- 5 linhas com track_artist/track_name/track_album_name nulos são descartadas antes de
  qualquer split em dimensões.
- playlist_id -> subgenre não é 1:1 no CSV bruto (8 de 471 playlists, 1,7%); resolvido
  pela moda de playlist_subgenre por playlist_id, com desempate pela primeira ocorrência
  no arquivo.
- track_playlist é deduplicado em (track_id, playlist_id): 582 linhas repetem o mesmo par
  com subgênero divergente -- não importa qual sobra, porque gênero não é armazenado
  nessa tabela.
- track_album_release_date tem 3 granularidades (dia completo / ano-mês / só ano);
  partes ausentes são preenchidas com "01" e a granularidade original fica registrada em
  albums.release_date_precision, para não disfarçar imputação como dado exato.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "spotify_songs.csv"

TRACK_FEATURE_COLUMNS = [
    "track_popularity",
    "duration_ms",
    "danceability",
    "energy",
    "key",
    "loudness",
    "mode",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
]


def get_engine():
    load_dotenv()
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def load_raw(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    before = len(df)
    df = df.dropna(subset=["track_artist", "track_name", "track_album_name"])
    print(f"[load_raw] {before} linhas lidas, {before - len(df)} descartadas (nulos), {len(df)} restantes")
    return df


def parse_release_date(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    raw = raw.astype(str)
    precision = pd.Series("day", index=raw.index)
    precision[raw.str.len() == 7] = "month"
    precision[raw.str.len() == 4] = "year"
    date = pd.to_datetime(raw, format="mixed").dt.date
    return date, precision


def build_genres(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"genre_name": df["playlist_genre"].unique()})


def build_subgenres(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[["playlist_subgenre", "playlist_genre"]].drop_duplicates(subset="playlist_subgenre")
    return sub.rename(columns={"playlist_subgenre": "subgenre_name", "playlist_genre": "genre_name"})


def build_artists(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"artist_name": df["track_artist"].unique()})


def build_albums(df: pd.DataFrame) -> pd.DataFrame:
    albums = df.drop_duplicates(subset="track_album_id")[
        ["track_album_id", "track_album_name", "track_album_release_date"]
    ].copy()
    albums["release_date"], albums["release_date_precision"] = parse_release_date(
        albums["track_album_release_date"]
    )
    albums = albums.rename(columns={"track_album_id": "album_id", "track_album_name": "album_name"})
    return albums[["album_id", "album_name", "release_date", "release_date_precision"]]


def resolve_playlist_subgenre(df: pd.DataFrame) -> pd.DataFrame:
    """Moda de playlist_subgenre por playlist_id, desempate pela 1a ocorrência no arquivo."""
    ordered = df[["playlist_id", "playlist_subgenre"]].copy()
    ordered["_order"] = range(len(ordered))
    counts = (
        ordered.groupby(["playlist_id", "playlist_subgenre"])
        .agg(n=("playlist_subgenre", "size"), first_seen=("_order", "min"))
        .reset_index()
        .sort_values(["playlist_id", "n", "first_seen"], ascending=[True, False, True])
    )
    winners = counts.drop_duplicates(subset="playlist_id", keep="first")
    return winners[["playlist_id", "playlist_subgenre"]]


def build_playlists(df: pd.DataFrame) -> pd.DataFrame:
    names = df.drop_duplicates(subset="playlist_id")[["playlist_id", "playlist_name"]]
    winners = resolve_playlist_subgenre(df)
    playlists = names.merge(winners, on="playlist_id", how="left")
    return playlists.rename(columns={"playlist_subgenre": "subgenre_name"})


def build_tracks(df: pd.DataFrame) -> pd.DataFrame:
    tracks = df.drop_duplicates(subset="track_id")[
        ["track_id", "track_name", "track_artist", "track_album_id", *TRACK_FEATURE_COLUMNS]
    ].copy()
    return tracks.rename(
        columns={
            "track_artist": "artist_name",
            "track_album_id": "album_id",
            "track_popularity": "popularity",
        }
    )


def build_track_playlist(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop_duplicates(subset=["track_id", "playlist_id"])[["track_id", "playlist_id"]]


def load_dimension(df: pd.DataFrame, table: str, engine, id_col: str, natural_col: str) -> pd.DataFrame:
    """Insere uma dimensão com PK serial e retorna o mapa {natural_col -> id_col} via re-SELECT."""
    df.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=1000)
    id_map = pd.read_sql(f"SELECT {id_col}, {natural_col} FROM {table}", engine)
    print(f"[load_dimension] {table}: {len(df)} linhas inseridas")
    return id_map


def main() -> None:
    engine = get_engine()
    df = load_raw(CSV_PATH)

    genre_map = load_dimension(build_genres(df), "genres", engine, "genre_id", "genre_name")

    subgenres = build_subgenres(df).merge(genre_map, on="genre_name", how="left")[["subgenre_name", "genre_id"]]
    subgenre_map = load_dimension(subgenres, "subgenres", engine, "subgenre_id", "subgenre_name")

    artist_map = load_dimension(build_artists(df), "artists", engine, "artist_id", "artist_name")

    albums = build_albums(df)
    albums.to_sql("albums", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[load] albums: {len(albums)} linhas inseridas")

    tracks = build_tracks(df).merge(artist_map, on="artist_name", how="left")
    tracks = tracks.drop(columns=["artist_name"])[
        [
            "track_id", "track_name", "artist_id", "album_id", "popularity",
            "duration_ms", "danceability", "energy", "key", "loudness", "mode",
            "speechiness", "acousticness", "instrumentalness", "liveness",
            "valence", "tempo",
        ]
    ]
    tracks.to_sql("tracks", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[load] tracks: {len(tracks)} linhas inseridas")

    playlists = build_playlists(df).merge(subgenre_map, on="subgenre_name", how="left")
    playlists = playlists[["playlist_id", "playlist_name", "subgenre_id"]]
    playlists.to_sql("playlists", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[load] playlists: {len(playlists)} linhas inseridas")

    track_playlist = build_track_playlist(df)
    track_playlist.to_sql(
        "track_playlist", engine, if_exists="append", index=False, method="multi", chunksize=1000
    )
    print(f"[load] track_playlist: {len(track_playlist)} linhas inseridas")

    print("Ingestão concluída.")


if __name__ == "__main__":
    main()

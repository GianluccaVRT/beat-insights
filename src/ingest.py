"""Ingestão da biblioteca Rekordbox real (Fase 1) para o schema em sql/schema/002_rekordbox_schema.sql.

Combina dois exports do Rekordbox, nenhum suficiente sozinho (ver docs/spec.md):
- Export_Playlists.xml (Collection + Playlists): PlayCount, Location, TrackID, estrutura de playlists.
- Playlists.txt (UTF-16, tab-separated): valores de MyTag, ausentes do XML.

Decisões de tratamento de dado, validadas contra a biblioteca real (1668 entradas na
Collection, 1649 em "All Tracks"):
- Escopo: qualquer TrackID presente na Collection mas ausente de "All Tracks" é
  descartado (19 casos na biblioteca de referência: loops de sample e gravações de
  set catalogadas por engano).
- Chave de merge entre os dois exports: (Name, Artist, DateAdded), com Artist vazio
  normalizado antes de comparar. "Name = Track Title" sozinho não é uma chave única --
  3 colisões reais na biblioteca de referência (mesmo título, TrackIDs diferentes:
  remixes/formatos distintos do mesmo release, e uma duplicata genuína) geram um
  cartesiano espúrio num merge ingênuo por título. A chave composta resolve os 3
  casos para um merge 1:1 exato.
- rating do XML vem codificado como 0/51/102/153/204/255 (não 0-5 direto) --
  decodificado via divisão inteira por 51.
- "All Tracks" nunca é inserida em playlists/track_playlist: é usada só como filtro
  de escopo, não como playlist de negócio (senão toda faixa teria uma linha
  redundante apontando pra ela).
- Estrutura de playlists é flat (nenhum nó Type="0"/pasta abaixo do ROOT na
  biblioteca de referência) -- sem tabela de hierarquia.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
XML_PATH = DATA_RAW / "Export_Playlists.xml"
TXT_PATH = DATA_RAW / "Playlists.txt"

ALL_TRACKS_PLAYLIST = "All Tracks"


def get_engine():
    load_dotenv()
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def parse_collection(xml_path: Path) -> pd.DataFrame:
    root = ET.parse(xml_path).getroot()
    rows = []
    for t in root.find("COLLECTION").findall("TRACK"):
        rows.append(
            {
                "track_id": int(t.get("TrackID")),
                "name": t.get("Name"),
                "artist": t.get("Artist") or "",
                "key_camelot": t.get("Tonality") or None,
                "bpm": float(t.get("AverageBpm")) if t.get("AverageBpm") else None,
                "genre": t.get("Genre") or None,
                "kind": t.get("Kind") or None,
                "duration_seconds": int(t.get("TotalTime")) if t.get("TotalTime") else None,
                "file_path": unquote(t.get("Location") or "").replace("file://localhost", ""),
                "date_added": t.get("DateAdded"),
                "play_count": int(t.get("PlayCount") or 0),
                "rating_raw": int(t.get("Rating") or 0),
            }
        )
    df = pd.DataFrame(rows)
    df["rating"] = df["rating_raw"] // 51
    return df.drop(columns="rating_raw")


def parse_playlists(xml_path: Path) -> tuple[pd.DataFrame, dict[str, set[str]]]:
    """Retorna (metadados de playlist, {nome_playlist: {track_id, ...}}). Estrutura assumida flat."""
    root = ET.parse(xml_path).getroot()
    meta_rows = []
    membership: dict[str, set[str]] = {}
    for node in root.find("PLAYLISTS").iter("NODE"):
        if node.get("Type") != "1":
            continue
        name = node.get("Name")
        track_ids = {int(trk.get("Key")) for trk in node.findall("TRACK")}
        meta_rows.append({"playlist_name": name, "entries": len(track_ids)})
        membership[name] = track_ids
    return pd.DataFrame(meta_rows), membership


def parse_mytag(txt_path: Path) -> pd.DataFrame:
    df = pd.read_csv(txt_path, sep="\t", encoding="utf-16")
    df["Artist"] = df["Artist"].fillna("")
    return df[["Track Title", "Artist", "Date Added", "My Tag"]]


def build_tracks(collection_df: pd.DataFrame, all_track_ids: set[int]) -> pd.DataFrame:
    scoped = collection_df[collection_df.track_id.isin(all_track_ids)].copy()
    print(
        f"[build_tracks] Collection: {len(collection_df)}, "
        f"excluídas (fora de 'All Tracks'): {len(collection_df) - len(scoped)}, "
        f"restantes: {len(scoped)}"
    )
    return scoped


def build_playlists(playlist_meta: pd.DataFrame) -> pd.DataFrame:
    playlists = playlist_meta[playlist_meta.playlist_name != ALL_TRACKS_PLAYLIST]
    return playlists[["playlist_name"]].reset_index(drop=True)


def build_track_playlist(membership: dict[str, set[str]], playlist_map: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, track_ids in membership.items():
        if name == ALL_TRACKS_PLAYLIST:
            continue
        playlist_id = playlist_map.loc[playlist_map.playlist_name == name, "playlist_id"].iloc[0]
        rows.extend({"track_id": tid, "playlist_id": playlist_id} for tid in track_ids)
    return pd.DataFrame(rows)


def merge_mytag(tracks_df: pd.DataFrame, mytag_df: pd.DataFrame) -> pd.DataFrame:
    merged = tracks_df.merge(
        mytag_df,
        left_on=["name", "artist", "date_added"],
        right_on=["Track Title", "Artist", "Date Added"],
        how="left",
    )
    unmatched = merged["Track Title"].isna().sum()
    if unmatched:
        print(f"[merge_mytag] AVISO: {unmatched} faixas sem correspondência no TXT (sem MyTag disponível)")
    return merged


def build_mytag_values(merged_df: pd.DataFrame) -> pd.DataFrame:
    all_tags = (
        merged_df["My Tag"].dropna().str.split(" / ").explode().str.strip()
    )
    all_tags = all_tags[all_tags != ""].unique()
    return pd.DataFrame({"value_name": sorted(all_tags)})


def build_track_mytag(merged_df: pd.DataFrame, value_map: pd.DataFrame) -> pd.DataFrame:
    exploded = merged_df[["track_id", "My Tag"]].dropna(subset=["My Tag"]).copy()
    exploded["value_name"] = exploded["My Tag"].str.split(" / ")
    exploded = exploded.explode("value_name")
    exploded["value_name"] = exploded["value_name"].str.strip()
    exploded = exploded[exploded["value_name"] != ""]
    return exploded.merge(value_map, on="value_name")[["track_id", "value_id"]]


def load_dimension(df: pd.DataFrame, table: str, engine, id_col: str, natural_col: str) -> pd.DataFrame:
    """Insere uma dimensão com PK serial e retorna o mapa {natural_col -> id_col} via re-SELECT."""
    df.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=1000)
    id_map = pd.read_sql(f"SELECT {id_col}, {natural_col} FROM {table}", engine)
    print(f"[load_dimension] {table}: {len(df)} linhas inseridas")
    return id_map


def main() -> None:
    engine = get_engine()

    collection_df = parse_collection(XML_PATH)
    playlist_meta, membership = parse_playlists(XML_PATH)
    mytag_df = parse_mytag(TXT_PATH)

    all_track_ids = membership[ALL_TRACKS_PLAYLIST]
    tracks_df = build_tracks(collection_df, all_track_ids)

    tracks_df.to_sql("tracks", engine, if_exists="append", index=False, method="multi", chunksize=500)
    print(f"[load] tracks: {len(tracks_df)} linhas inseridas")

    playlists_df = build_playlists(playlist_meta)
    playlist_map = load_dimension(playlists_df, "playlists", engine, "playlist_id", "playlist_name")

    track_playlist_df = build_track_playlist(membership, playlist_map)
    track_playlist_df.to_sql(
        "track_playlist", engine, if_exists="append", index=False, method="multi", chunksize=1000
    )
    print(f"[load] track_playlist: {len(track_playlist_df)} linhas inseridas")

    merged_df = merge_mytag(tracks_df, mytag_df)
    mytag_values_df = build_mytag_values(merged_df)
    value_map = load_dimension(mytag_values_df, "mytag_values", engine, "value_id", "value_name")

    track_mytag_df = build_track_mytag(merged_df, value_map)
    track_mytag_df.to_sql(
        "track_mytag", engine, if_exists="append", index=False, method="multi", chunksize=1000
    )
    print(f"[load] track_mytag: {len(track_mytag_df)} linhas inseridas")

    print("Ingestão concluída.")


if __name__ == "__main__":
    main()

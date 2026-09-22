"""Recomputa as métricas de silhouette/ARI do baseline (V1/V2/V3) a partir dos
rótulos já persistidos em track_clusters, sem retreinar KMeans nem escrever no
banco -- só leitura. Existe pra que os números citados em results/ e no README
tenham um script que os reproduz, em vez de serem transcritos de memória/prosa.

Rodar: python src/verify_baseline.py
"""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sqlalchemy import text

import cluster_v1
import cluster_v2
import cluster_v3
import ingest
from clustering_common import get_engine

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "baseline_2026-09"


def verify_ingestion(today: str) -> list[dict]:
    """Reparseia o XML/TXT (leitura, não escreve nada) e confere contra o banco --
    verifica os números de ingestão do mesmo jeito que verify_baseline confere os
    de clustering: recomputando, não confiando na prosa do README."""
    entries = []

    def entry(metric, valor, valor_claimed, script_gerador, observacao=""):
        match = "sim" if valor == valor_claimed else "NAO -- ver observacao"
        return {
            "metric": metric,
            "espaco": None,
            "valor": valor,
            "valor_claimed_no_readme": valor_claimed,
            "bate_com_readme": match,
            "data_verificacao": today,
            "script_gerador_original": script_gerador,
            "script_que_recomputou": "src/verify_baseline.py",
            "observacao": observacao,
        }

    collection_df = ingest.parse_collection(ingest.XML_PATH)
    _playlist_meta, membership = ingest.parse_playlists(ingest.XML_PATH)
    all_track_ids = membership[ingest.ALL_TRACKS_PLAYLIST]

    entries.append(entry("collection_entradas", len(collection_df), 1668, "ingest.py (reparse do XML)"))
    entries.append(entry("all_tracks_entradas", len(all_track_ids), 1649, "ingest.py (reparse do XML)"))
    entries.append(
        entry(
            "faixas_excluidas_escopo",
            len(collection_df) - len(all_track_ids),
            19,
            "ingest.py (reparse do XML)",
        )
    )

    engine = get_engine()
    with engine.connect() as conn:
        n_tracks = conn.execute(text("SELECT count(*) FROM tracks")).scalar()
        n_playlists = conn.execute(text("SELECT count(*) FROM playlists")).scalar()
        n_track_playlist = conn.execute(text("SELECT count(*) FROM track_playlist")).scalar()
        n_mytag_values = conn.execute(text("SELECT count(*) FROM mytag_values")).scalar()
        n_track_mytag = conn.execute(text("SELECT count(*) FROM track_mytag")).scalar()
        n_faixas_com_tag = conn.execute(text("SELECT count(DISTINCT track_id) FROM track_mytag")).scalar()

    entries.append(entry("tracks_no_banco", n_tracks, 1649, "ingest.py (consulta direta à tabela tracks)"))
    entries.append(entry("playlists_no_banco", n_playlists, 13, "ingest.py (consulta direta)"))
    entries.append(entry("vinculos_track_playlist", n_track_playlist, 1134, "ingest.py (consulta direta)"))
    entries.append(entry("mytag_valores_unicos", n_mytag_values, 44, "ingest.py (consulta direta)"))
    entries.append(entry("vinculos_track_mytag", n_track_mytag, 1617, "ingest.py (consulta direta)"))
    entries.append(entry("faixas_com_pelo_menos_1_tag", n_faixas_com_tag, 333, "ingest.py (consulta direta)"))
    return entries


def load_labels(engine, version: str) -> pd.Series:
    return pd.read_sql(
        text("SELECT track_id, cluster_label FROM track_clusters WHERE cluster_version = :v"),
        engine,
        params={"v": version},
    ).set_index("track_id")["cluster_label"]


def ari_between(labels_a: pd.Series, labels_b: pd.Series) -> tuple[float, int]:
    common = labels_a.index.intersection(labels_b.index)
    return adjusted_rand_score(labels_a.loc[common], labels_b.loc[common]), len(common)


def main() -> None:
    engine = get_engine()
    tracks, mytag = cluster_v1.load_data(engine)
    audio = cluster_v2.load_audio_features(engine)

    features_v1 = cluster_v1.build_features(tracks, mytag)
    features_v2 = cluster_v2.build_features(tracks, mytag, audio)
    features_v3 = cluster_v3.build_features(audio)

    labels_v1 = load_labels(engine, "v1_structured").loc[features_v1.index]
    labels_v2 = load_labels(engine, "v2_audio").loc[features_v2.index]
    labels_v3 = load_labels(engine, "v3_audio_only").loc[features_v3.index]

    sil_v1 = silhouette_score(features_v1, labels_v1)
    sil_v2 = silhouette_score(features_v2, labels_v2)
    sil_v3 = silhouette_score(features_v3, labels_v3)

    ari_v1_v2, n_12 = ari_between(labels_v1, labels_v2)
    ari_v3_v2, n_32 = ari_between(labels_v3, labels_v2)
    ari_v3_v1, n_31 = ari_between(labels_v3, labels_v1)

    today = date.today().isoformat()

    def entry(metric, espaco, valor, valor_claimed, script_gerador, observacao=""):
        # README arredonda pra 3 casas decimais -- tolerância de arredondamento,
        # não de valor: só sinaliza divergência real (diferença > 0.001).
        match = "sim" if abs(valor - valor_claimed) < 0.001 else "NAO -- ver observacao"
        return {
            "metric": metric,
            "espaco": espaco,
            "valor": round(float(valor), 4),
            "valor_claimed_no_readme": valor_claimed,
            "bate_com_readme": match,
            "data_verificacao": today,
            "script_gerador_original": script_gerador,
            "script_que_recomputou": "src/verify_baseline.py",
            "observacao": observacao,
        }

    ingestion_metrics = verify_ingestion(today)

    metrics = ingestion_metrics + [
        entry("n_faixas", "meta", len(features_v1), 1649, "cluster_v1.py"),
        entry("n_features", "meta", features_v1.shape[1], 83, "cluster_v1.py"),
        entry("silhouette", "meta", sil_v1, 0.368, "cluster_v1.py"),
        entry("n_faixas", "meta_audio", len(features_v2), 1648, "cluster_v2.py"),
        entry("n_features", "meta_audio", features_v2.shape[1], 111, "cluster_v2.py"),
        entry("silhouette", "meta_audio", sil_v2, 0.072, "cluster_v2.py"),
        entry("n_faixas", "audio", len(features_v3), 1648, "cluster_v3.py"),
        entry("n_features", "audio", features_v3.shape[1], 28, "cluster_v3.py"),
        entry("silhouette", "audio", sil_v3, 0.080, "cluster_v3.py"),
        entry("ari_meta_x_meta_audio", "meta x meta_audio", ari_v1_v2, 0.019, "cluster_v2.py",
              f"{n_12} faixas em comum"),
        entry("ari_audio_x_meta_audio", "audio x meta_audio", ari_v3_v2, 0.909, "cluster_v3.py",
              f"{n_32} faixas em comum"),
        entry("ari_audio_x_meta", "audio x meta", ari_v3_v1, 0.009, "cluster_v3.py",
              f"{n_31} faixas em comum"),
    ]

    for m in metrics:
        flag = "" if m["bate_com_readme"] == "sim" else "  <-- DIVERGE"
        print(f"[{m['espaco'] or '-'}] {m['metric']} = {m['valor']} (README: {m['valor_claimed_no_readme']}){flag}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "metrics.json"
    payload = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "descricao": (
            "Métricas do baseline V1/V2/V3 (Fase 3) e da ingestão, recomputadas nesta sessão "
            "-- reparse read-only do XML/TXT pra ingestão, e silhouette/ARI recalculados a "
            "partir dos rótulos já persistidos em track_clusters (v1_structured/v2_audio/"
            "v3_audio_only) sem retreinar KMeans. Nada foi escrito no banco por este script."
        ),
        "metrics": metrics,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[verify_baseline] gravado em {out_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

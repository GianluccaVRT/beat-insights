"""Extração de features de áudio (Fase 3, V2) via librosa, uma faixa por vez.

Decisões:
- Janela de análise: 60s a partir do segundo 15 de cada faixa (não a faixa inteira).
  Testado contra a biblioteca real: decodificar a faixa inteira (~1649 arquivos,
  maioria MP3) levaria bem mais tempo sem ganho de sinal proporcional -- 60s já
  captura tempo/timbre/harmonia de forma estável. offset=15 pula a maior parte de
  intros silenciosos/de baixa energia sem custo adicional de decode perceptível
  (testado: mesmo tempo de load que offset=0, porque o backend via ffmpeg faz seek,
  não decodifica e descarta). Se a faixa for mais curta que 75s, cai para offset=0.
- Gravação incremental (uma faixa por vez, não em lote no final): a extração leva
  da ordem de minutos a ~1h na biblioteca de referência (medido: ~2s/faixa), então
  o script é resumível -- reexecutar pula track_ids já presentes em audio_features.
- Falha por faixa (arquivo ausente, corrompido, formato não suportado) é logada e
  pulada, não interrompe o lote inteiro.
"""

import os
import time
from pathlib import Path

import librosa
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

SR = 22050
WINDOW_DURATION = 60
WINDOW_OFFSET = 15
MIN_DURATION_FOR_OFFSET = 75  # abaixo disso, usa offset=0
N_MFCC = 13
N_CHROMA = 12

FEATURE_COLUMNS = (
    ["tempo_detected", "spectral_centroid_mean", "rms_energy_mean"]
    + [f"mfcc_{i:02d}" for i in range(1, N_MFCC + 1)]
    + [f"chroma_{i:02d}" for i in range(1, N_CHROMA + 1)]
)


def get_engine():
    load_dotenv()
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def pending_tracks(engine) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT t.track_id, t.file_path, t.duration_seconds
        FROM tracks t
        LEFT JOIN audio_features af ON af.track_id = t.track_id
        WHERE af.track_id IS NULL
        ORDER BY t.track_id
        """,
        engine,
    )


def extract_features(file_path: str, duration_seconds: int | None) -> dict:
    offset = WINDOW_OFFSET if (duration_seconds or 0) >= MIN_DURATION_FOR_OFFSET else 0
    y, sr = librosa.load(file_path, sr=SR, offset=offset, duration=WINDOW_DURATION)
    if y.size == 0:
        raise ValueError("áudio vazio (arquivo mais curto que o esperado ou ilegível)")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    rms = float(librosa.feature.rms(y=y).mean())
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC).mean(axis=1)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr).mean(axis=1)

    row = {"tempo_detected": tempo, "spectral_centroid_mean": centroid, "rms_energy_mean": rms}
    row.update({f"mfcc_{i:02d}": float(v) for i, v in enumerate(mfcc, start=1)})
    row.update({f"chroma_{i:02d}": float(v) for i, v in enumerate(chroma, start=1)})
    return row


def insert_row(engine, track_id: int, features: dict) -> None:
    columns = ["track_id"] + FEATURE_COLUMNS
    placeholders = ", ".join(f":{c}" for c in columns)
    stmt = text(f"INSERT INTO audio_features ({', '.join(columns)}) VALUES ({placeholders})")
    with engine.begin() as conn:
        conn.execute(stmt, {"track_id": track_id, **features})


def main() -> None:
    engine = get_engine()
    todo = pending_tracks(engine)
    total = len(todo)
    print(f"[extract] {total} faixas pendentes (audio_features ainda não tem esse track_id)")

    ok, failed = 0, 0
    t_start = time.time()
    for i, row in enumerate(todo.itertuples(index=False), start=1):
        path = row.file_path
        try:
            if not Path(path).exists():
                raise FileNotFoundError(path)
            features = extract_features(path, row.duration_seconds)
            insert_row(engine, row.track_id, features)
            ok += 1
        except Exception as exc:  # noqa: BLE001 -- erro por faixa não pode derrubar o lote
            failed += 1
            print(f"[extract] FALHA track_id={row.track_id} ({path}): {exc}")

        if i % 50 == 0 or i == total:
            elapsed = time.time() - t_start
            rate = elapsed / i
            eta_min = rate * (total - i) / 60
            print(f"[extract] {i}/{total} processadas ({ok} ok, {failed} falhas) -- ETA {eta_min:.1f} min")

    print(f"[extract] concluído: {ok} ok, {failed} falhas de {total}")


if __name__ == "__main__":
    main()

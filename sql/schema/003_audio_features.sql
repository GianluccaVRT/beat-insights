-- Features de áudio extraídas via librosa (Fase 3, V2). Ver src/extract_audio_features.py
-- para a decisão de janela de análise (60s a partir do segundo 15, não a faixa
-- inteira -- ver rationale no cabeçalho do script).
CREATE TABLE audio_features (
    track_id                 INTEGER PRIMARY KEY REFERENCES tracks (track_id),
    tempo_detected            REAL,    -- pode divergir do BPM informado pela loja (tracks.bpm)
    spectral_centroid_mean    REAL,
    rms_energy_mean           REAL,
    mfcc_01 REAL, mfcc_02 REAL, mfcc_03 REAL, mfcc_04 REAL, mfcc_05 REAL,
    mfcc_06 REAL, mfcc_07 REAL, mfcc_08 REAL, mfcc_09 REAL, mfcc_10 REAL,
    mfcc_11 REAL, mfcc_12 REAL, mfcc_13 REAL,
    chroma_01 REAL, chroma_02 REAL, chroma_03 REAL, chroma_04 REAL,
    chroma_05 REAL, chroma_06 REAL, chroma_07 REAL, chroma_08 REAL,
    chroma_09 REAL, chroma_10 REAL, chroma_11 REAL, chroma_12 REAL
);

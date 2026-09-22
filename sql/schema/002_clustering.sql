-- Persistência dos resultados de clustering (Fase 3). cluster_version distingue V1
-- (só metadados estruturados) de V2 (metadados + features de áudio via librosa),
-- para permitir a comparação V1 x V2 pedida no roadmap sem sobrescrever resultados.
-- cluster_version VARCHAR(40): alargado de VARCHAR(20) na fase "3 espaços + k-NN"
-- (ADR-001) -- as versões novas incluem espaço+k+run (ex.: "meta_audio_k2_2026-09",
-- 22 caracteres), que não cabiam no limite original. ALTER não destrutivo, aplicado
-- em produção antes deste arquivo ser atualizado; rodar este CREATE TABLE do zero já
-- nasce com o limite certo.
CREATE TABLE track_clusters (
    track_id         INTEGER NOT NULL REFERENCES tracks (track_id),
    cluster_version  VARCHAR(40) NOT NULL,
    cluster_label    INTEGER NOT NULL,
    PRIMARY KEY (track_id, cluster_version)
);

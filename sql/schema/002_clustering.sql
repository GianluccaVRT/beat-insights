-- Persistência dos resultados de clustering (Fase 3). cluster_version distingue V1
-- (só metadados estruturados) de V2 (metadados + features de áudio via librosa),
-- para permitir a comparação V1 x V2 pedida no roadmap sem sobrescrever resultados.
CREATE TABLE track_clusters (
    track_id         INTEGER NOT NULL REFERENCES tracks (track_id),
    cluster_version  VARCHAR(20) NOT NULL,
    cluster_label    INTEGER NOT NULL,
    PRIMARY KEY (track_id, cluster_version)
);

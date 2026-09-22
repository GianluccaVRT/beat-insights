-- beat-insights: schema Fase 1 (biblioteca Rekordbox real)
-- Fonte: merge de data/raw/Export_Playlists.xml (Collection + Playlists) e
-- data/raw/Playlists.txt (MyTag). Ver docs/spec.md para os achados que embasam
-- as decisões abaixo; números validados contra a biblioteca real (1668 entradas
-- na Collection, 1649 em "All Tracks", 19 excluídas).

CREATE TABLE tracks (
    track_id          INTEGER PRIMARY KEY,   -- TrackID nativo do XML (Rekordbox)
    name              VARCHAR(255) NOT NULL, -- Name (XML) = Track Title (TXT), validado 100% idêntico
    artist            VARCHAR(255) NOT NULL DEFAULT '',
    key_camelot       VARCHAR(3),            -- Tonality (XML)
    bpm               REAL,                  -- AverageBpm (XML)
    genre             VARCHAR(100),
    kind              VARCHAR(20),           -- "MP3 File" / "WAV File" / "AIFF File"
    duration_seconds  INTEGER,
    file_path         TEXT,                  -- Location (XML), decodificado de URL-encoding
    date_added        DATE,
    play_count        INTEGER NOT NULL DEFAULT 0,
    rating             SMALLINT NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5)
);

CREATE TABLE playlists (
    playlist_id    SERIAL PRIMARY KEY,   -- sem ID nativo no XML (só Name), gerado na ingestão
    playlist_name  VARCHAR(255) NOT NULL UNIQUE
);
-- Nota: "All Tracks" não é inserida aqui -- é usada só como filtro de escopo
-- durante a ingestão (define o conjunto de track_id válido), não como uma
-- playlist de negócio. Ver docs/spec.md.

CREATE TABLE track_playlist (
    track_id     INTEGER NOT NULL REFERENCES tracks (track_id),
    playlist_id  INTEGER NOT NULL REFERENCES playlists (playlist_id),
    PRIMARY KEY (track_id, playlist_id)
);
CREATE INDEX idx_track_playlist_playlist_id ON track_playlist (playlist_id);

CREATE TABLE mytag_values (
    value_id    SERIAL PRIMARY KEY,
    value_name  VARCHAR(100) NOT NULL UNIQUE
);
-- Sem tabela de grupo/categoria: confirmado com a biblioteca real que o
-- Rekordbox não expõe a qual grupo cada valor de MyTag pertence, em nenhum
-- export -- lista plana é a representação fiel ao dado disponível.

CREATE TABLE track_mytag (
    track_id  INTEGER NOT NULL REFERENCES tracks (track_id),
    value_id  INTEGER NOT NULL REFERENCES mytag_values (value_id),
    PRIMARY KEY (track_id, value_id)
);

COMMENT ON TABLE tracks IS
    'Escopo = playlist "All Tracks" do XML, não a Collection inteira (19 entradas excluídas: loops de sample e gravações de set catalogadas por engano). rating é decodificado de Rating do XML (0/51/102/153/204/255 -> 0-5 estrelas).';
COMMENT ON TABLE mytag_values IS
    'MyTag só existe no export TXT (0 ocorrências no XML) -- limitação confirmada do Rekordbox, não erro de export.';

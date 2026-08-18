-- beat-insights: schema inicial (Projeto 1)
-- Fonte: "30000 Spotify Songs" (Kaggle: joebeachcapital/30000-spotify-songs)
--
-- Decisão: track_artist como coluna única (sem tabela de junção N:N artist<->track).
-- Checagem no CSV bruto (32.833 linhas): 854 linhas (2,6%) de track_artist contêm
-- separador candidato a multi-artista (",", ";", "feat.", "&", "with"), mas a
-- inspeção manual mostrou que a maioria é falso positivo -- o separador faz parte
-- do nome do ato (ex: "Dimitri Vegas & Like Mike", "Tyler, The Creator", "Sleeping
-- With Sirens" sao nomes de duo/banda unicos, nao dois artistas). Apenas "feat."
-- se mostrou confiavel como separador real (~11 linhas, 0,03% do total). Normalizar
-- cobriria menos de 0,1% das linhas e exigiria lista de exceçoes curada a mao para
-- nao corromper nomes de duo/banda -- custo desproporcional ao ganho. Ver docs/spec.md.
-- Limitação conhecida: contagem "top artistas" subestima faixas com feature.
--
-- Decisão: albums.release_date_precision ('day'|'month'|'year'). O CSV bruto tem
-- track_album_release_date em 3 granularidades: data completa (94,3%), ano-mês
-- (0,09%) e só ano (5,65%, 1.855 linhas). Preencher dia/mês ausentes como "01" sem
-- marcar a precisão distorceria qualquer agregação mensal (viés artificial em
-- janeiro para 5,75% dos álbuns) sem deixar rastro de que é artefato de imputação,
-- não dado real -- inaceitável num projeto cujo objetivo é demonstrar análise
-- temporal via SQL. VARCHAR + CHECK em vez de tipo ENUM nativo do Postgres: só 3
-- valores fixos, e CHECK evita o custo de CREATE TYPE/ALTER TYPE para algo dessa
-- escala. Ver docs/spec.md para os números completos.

CREATE TABLE genres (
    genre_id    SERIAL PRIMARY KEY,
    genre_name  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE subgenres (
    subgenre_id    SERIAL PRIMARY KEY,
    subgenre_name  VARCHAR(100) NOT NULL UNIQUE,
    genre_id       INTEGER NOT NULL REFERENCES genres (genre_id)
);

CREATE TABLE artists (
    artist_id    SERIAL PRIMARY KEY,
    artist_name  VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE albums (
    album_id               VARCHAR(64) PRIMARY KEY,
    album_name             VARCHAR(255) NOT NULL,
    release_date           DATE,
    release_date_precision VARCHAR(5) NOT NULL DEFAULT 'day'
        CHECK (release_date_precision IN ('day', 'month', 'year'))
);

CREATE TABLE tracks (
    track_id          VARCHAR(64) PRIMARY KEY,
    track_name        VARCHAR(255) NOT NULL,
    artist_id         INTEGER NOT NULL REFERENCES artists (artist_id),
    album_id          VARCHAR(64) NOT NULL REFERENCES albums (album_id),
    popularity        SMALLINT,
    duration_ms       INTEGER,
    danceability      REAL,
    energy            REAL,
    key               SMALLINT,
    loudness          REAL,
    mode              SMALLINT,
    speechiness       REAL,
    acousticness      REAL,
    instrumentalness  REAL,
    liveness          REAL,
    valence           REAL,
    tempo             REAL
);

CREATE TABLE playlists (
    playlist_id    VARCHAR(64) PRIMARY KEY,
    playlist_name  VARCHAR(255) NOT NULL,
    subgenre_id    INTEGER NOT NULL REFERENCES subgenres (subgenre_id)
);

-- Junção N:N: no CSV bruto, cada linha é um par (track, playlist) -- a mesma
-- track_id se repete se a faixa aparece em playlists diferentes.
CREATE TABLE track_playlist (
    track_id     VARCHAR(64) NOT NULL REFERENCES tracks (track_id),
    playlist_id  VARCHAR(64) NOT NULL REFERENCES playlists (playlist_id),
    PRIMARY KEY (track_id, playlist_id)
);

-- Índices adicionais
-- albums.release_date: não é única (muitos álbuns por data) -- índice de valor
-- repetido, usado para filtros/ordenação por período nas queries de tendência.
CREATE INDEX idx_albums_release_date ON albums (release_date);

-- genres.genre_name e subgenres.subgenre_name já têm índice implícito via UNIQUE
-- (Postgres cria um índice btree automaticamente para toda constraint UNIQUE) --
-- não criamos um CREATE INDEX redundante aqui, pois duplicaria estrutura sem
-- ganho e adicionaria overhead de escrita à toa.

-- track_playlist.playlist_id: a PK composta (track_id, playlist_id) gera um
-- índice cujo prefixo esquerdo é track_id -- útil para "playlists de uma faixa",
-- mas inútil para buscas por playlist_id isolado ("faixas de uma playlist").
-- Esse índice extra cobre essa direção da consulta.
CREATE INDEX idx_track_playlist_playlist_id ON track_playlist (playlist_id);

-- Comentários de catálogo: por que misturamos chave natural (ID do Spotify) com
-- chave surrogate (serial) entre as tabelas.
COMMENT ON TABLE albums IS
    'PK = album_id nativo do Spotify (chave natural). O Spotify já garante unicidade e estabilidade desse ID, então um serial adicional só criaria um join sem necessidade.';
COMMENT ON TABLE tracks IS
    'PK = track_id nativo do Spotify (chave natural), mesma lógica de albums/playlists. artist_id aponta para uma única linha em artists por faixa -- ver nota sobre track_artist no topo do arquivo: não há tabela de junção multi-artista.';
COMMENT ON TABLE playlists IS
    'PK = playlist_id nativo do Spotify (chave natural).';
COMMENT ON TABLE artists IS
    'PK = artist_id serial (surrogate). track_artist é texto livre vindo do CSV, sem garantia de unicidade/estabilidade (risco de variação de grafia/encoding entre linhas), por isso não é usado como chave natural.';
COMMENT ON TABLE genres IS
    'PK = genre_id serial (surrogate). playlist_genre no CSV é texto livre, sem ID nativo do Spotify associado -- diferente de tracks/albums/playlists, aqui não existe chave natural estável para reaproveitar.';
COMMENT ON TABLE subgenres IS
    'PK = subgenre_id serial (surrogate), mesma razão de genres. FK genre_id: cada subgênero pertence a exatamente 1 gênero (hierarquia 1:N, não N:N), por isso é FK direto e não uma tabela de junção.';
COMMENT ON COLUMN tracks.artist_id IS
    'Um artista por faixa (sem split de colaborações/"feat."). Ver nota no topo do arquivo e docs/spec.md para os números da checagem que embasaram essa decisão.';
COMMENT ON COLUMN albums.release_date_precision IS
    'Granularidade original da data no CSV fonte (day/month/year). release_date sempre vem preenchido com dia/mês default "01" quando o CSV só tinha ano ou ano-mês -- esta coluna marca isso como artefato de imputação, para não distorcer agregações mensais silenciosamente. Ver nota no topo do arquivo.';

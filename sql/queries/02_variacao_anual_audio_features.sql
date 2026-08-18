-- Pergunta de negócio: como a energia e a dançabilidade média das faixas evoluem ano a
-- ano, por gênero? Mostra se o público está migrando pra sons mais "empolgantes/dançantes"
-- ou mais "carregados" ao longo do tempo, gênero por gênero.
--
-- Sem filtro de release_date_precision: agregamos por ANO inteiro (EXTRACT(YEAR)), e o
-- ano em si é sempre correto mesmo em álbuns com precisão 'month' ou 'year' -- só dia/mês
-- são imputados, nunca o ano. O viés de imputação só afeta granularidade sub-anual
-- (trimestre/mês), tratado nas queries 03, 05 e 08.
--
-- Window function: LAG() OVER (PARTITION BY genre_name ORDER BY release_year) -- compara
-- cada ano com o ano imediatamente anterior dentro do mesmo gênero.

WITH yearly_stats AS (
    SELECT
        g.genre_name,
        EXTRACT(YEAR FROM al.release_date)::INT AS release_year,
        AVG(t.energy) AS avg_energy,
        AVG(t.danceability) AS avg_danceability
    FROM tracks t
    JOIN albums al ON al.album_id = t.album_id
    JOIN track_playlist tp ON tp.track_id = t.track_id
    JOIN playlists p ON p.playlist_id = tp.playlist_id
    JOIN subgenres sg ON sg.subgenre_id = p.subgenre_id
    JOIN genres g ON g.genre_id = sg.genre_id
    GROUP BY g.genre_name, EXTRACT(YEAR FROM al.release_date)
)
SELECT
    genre_name,
    release_year,
    ROUND(avg_energy::NUMERIC, 3) AS avg_energy,
    ROUND(avg_danceability::NUMERIC, 3) AS avg_danceability,
    ROUND(
        (avg_energy - LAG(avg_energy) OVER (PARTITION BY genre_name ORDER BY release_year))::NUMERIC,
        3
    ) AS energy_change_vs_prev_year,
    ROUND(
        (avg_danceability - LAG(avg_danceability) OVER (PARTITION BY genre_name ORDER BY release_year))::NUMERIC,
        3
    ) AS danceability_change_vs_prev_year
FROM yearly_stats
ORDER BY genre_name, release_year;

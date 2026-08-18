-- Pergunta de negócio: qual a tendência de popularidade média por trimestre de
-- lançamento, por gênero, suavizada por média móvel? Uma média móvel evita reagir a um
-- pico ou vale isolado de um único trimestre, mostrando a tendência de fundo.
--
-- Filtro release_date_precision != 'year': agregamos por TRIMESTRE (DATE_TRUNC('quarter',
-- ...)), granularidade sub-anual. Álbuns com precisão 'year' têm dia/mês imputados como
-- 01/01 e cairiam artificialmente todos no Q1 do seu ano, distorcendo a série trimestral.
-- Álbuns com precisão 'month' entram, porque o trimestre continua correto mesmo com o dia
-- imputado (dia 1 de um mês real ainda aponta pro trimestre certo).
--
-- Window function: AVG() OVER com frame de linhas (ROWS BETWEEN 3 PRECEDING AND CURRENT
-- ROW) -- média móvel de 4 trimestres (o trimestre atual + os 3 anteriores).

WITH quarterly_stats AS (
    SELECT
        g.genre_name,
        DATE_TRUNC('quarter', al.release_date)::DATE AS release_quarter,
        AVG(t.popularity) AS avg_popularity
    FROM tracks t
    JOIN albums al ON al.album_id = t.album_id
    JOIN track_playlist tp ON tp.track_id = t.track_id
    JOIN playlists p ON p.playlist_id = tp.playlist_id
    JOIN subgenres sg ON sg.subgenre_id = p.subgenre_id
    JOIN genres g ON g.genre_id = sg.genre_id
    WHERE al.release_date_precision != 'year'
    GROUP BY g.genre_name, DATE_TRUNC('quarter', al.release_date)
)
SELECT
    genre_name,
    release_quarter,
    ROUND(avg_popularity::NUMERIC, 2) AS avg_popularity,
    ROUND(
        AVG(avg_popularity) OVER (
            PARTITION BY genre_name
            ORDER BY release_quarter
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        )::NUMERIC,
        2
    ) AS moving_avg_4_quarters
FROM quarterly_stats
ORDER BY genre_name, release_quarter;

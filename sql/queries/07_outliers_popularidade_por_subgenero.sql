-- Pergunta de negócio: quais faixas mais se destacam (positiva ou negativamente) da
-- popularidade média do seu subgênero? Sinaliza tanto "hits inesperados" (faixa muito
-- mais popular que o nicho costuma performar) quanto faixas que performam bem abaixo do
-- esperado para o subgênero -- os "top 10 outliers" citados no objetivo original do
-- projeto (docs/spec.md).

WITH track_subgenre AS (
    SELECT DISTINCT
        t.track_id,
        t.track_name,
        a.artist_name,
        t.popularity,
        sg.subgenre_name
    FROM tracks t
    JOIN artists a ON a.artist_id = t.artist_id
    JOIN track_playlist tp ON tp.track_id = t.track_id
    JOIN playlists p ON p.playlist_id = tp.playlist_id
    JOIN subgenres sg ON sg.subgenre_id = p.subgenre_id
),
deviations AS (
    SELECT
        subgenre_name,
        track_name,
        artist_name,
        popularity,
        ROUND(AVG(popularity) OVER (PARTITION BY subgenre_name)::NUMERIC, 2) AS subgenre_avg_popularity,
        ROUND(
            (popularity - AVG(popularity) OVER (PARTITION BY subgenre_name))::NUMERIC,
            2
        ) AS deviation
    FROM track_subgenre
)
SELECT subgenre_name, track_name, artist_name, popularity, subgenre_avg_popularity, deviation
FROM deviations
ORDER BY ABS(deviation) DESC
LIMIT 10;

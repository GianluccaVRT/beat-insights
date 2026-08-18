-- Pergunta de negócio: quais são as faixas mais populares dentro de cada subgênero de
-- música eletrônica (progressive electro house, electro house, big room, pop edm)?
-- Útil para identificar as "faixas-âncora" de cada nicho de EDM -- o que definitivamente
-- não pode faltar num set do subgênero.
--
-- Window function: DENSE_RANK() OVER (PARTITION BY subgenre_name ORDER BY popularity DESC)
-- -- ranking dentro de cada grupo, sem pular posições em caso de empate de popularidade
-- (diferente de RANK(), que deixaria buracos na numeração).

WITH edm_tracks AS (
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
    JOIN genres g ON g.genre_id = sg.genre_id
    WHERE g.genre_name = 'edm'
),
ranked AS (
    SELECT
        subgenre_name,
        track_name,
        artist_name,
        popularity,
        DENSE_RANK() OVER (PARTITION BY subgenre_name ORDER BY popularity DESC) AS rank_in_subgenre
    FROM edm_tracks
)
SELECT subgenre_name, rank_in_subgenre, track_name, artist_name, popularity
FROM ranked
WHERE rank_in_subgenre <= 5
ORDER BY subgenre_name, rank_in_subgenre;

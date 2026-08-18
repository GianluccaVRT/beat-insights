-- Pergunta de negócio: quais artistas produzem consistentemente para múltiplos
-- subgêneros de EDM (não só um hit isolado num nicho)? Indica quem realmente "segue a
-- tendência" do gênero como um todo, versus artista de nicho único.
--
-- CTE encadeada (2 WITH): a primeira agrega contagem de faixas distintas por
-- (artista, subgênero); a segunda filtra artistas presentes em >= 2 subgêneros de EDM
-- antes do ranking final. Sem os 2 passos, seria necessário aninhar uma subquery de
-- agregação dentro de uma subquery de filtro dentro de uma de ranking -- ilegível.

WITH artist_subgenre_counts AS (
    SELECT
        a.artist_id,
        a.artist_name,
        sg.subgenre_name,
        COUNT(DISTINCT t.track_id) AS n_tracks
    FROM tracks t
    JOIN artists a ON a.artist_id = t.artist_id
    JOIN track_playlist tp ON tp.track_id = t.track_id
    JOIN playlists p ON p.playlist_id = tp.playlist_id
    JOIN subgenres sg ON sg.subgenre_id = p.subgenre_id
    JOIN genres g ON g.genre_id = sg.genre_id
    WHERE g.genre_name = 'edm'
    GROUP BY a.artist_id, a.artist_name, sg.subgenre_name
),
multi_subgenre_artists AS (
    SELECT
        artist_id,
        artist_name,
        COUNT(DISTINCT subgenre_name) AS n_subgenres,
        SUM(n_tracks) AS total_tracks
    FROM artist_subgenre_counts
    GROUP BY artist_id, artist_name
    HAVING COUNT(DISTINCT subgenre_name) >= 2
)
SELECT artist_name, n_subgenres, total_tracks
FROM multi_subgenre_artists
ORDER BY n_subgenres DESC, total_tracks DESC
LIMIT 20;

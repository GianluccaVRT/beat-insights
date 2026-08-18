-- Pergunta de negócio: existe um mês do ano em que cada gênero concentra mais
-- lançamentos (sazonalidade)? Ex: EDM lançando mais faixas antes da temporada de
-- festivais de verão no hemisfério norte.
--
-- Filtro release_date_precision IN ('day', 'month'): álbuns com precisão 'month' têm o
-- mês REAL conhecido (só o dia foi imputado) -- excluí-los descartaria dado válido sem
-- necessidade. Só 'year' é excluído: nesse caso o mês inteiro foi imputado como 01,
-- então contar esses álbuns inflaria janeiro artificialmente.

SELECT
    g.genre_name,
    EXTRACT(MONTH FROM al.release_date)::INT AS release_month,
    COUNT(DISTINCT t.track_id) AS n_tracks
FROM tracks t
JOIN albums al ON al.album_id = t.album_id
JOIN track_playlist tp ON tp.track_id = t.track_id
JOIN playlists p ON p.playlist_id = tp.playlist_id
JOIN subgenres sg ON sg.subgenre_id = p.subgenre_id
JOIN genres g ON g.genre_id = sg.genre_id
WHERE al.release_date_precision IN ('day', 'month')
GROUP BY g.genre_name, EXTRACT(MONTH FROM al.release_date)
ORDER BY g.genre_name, release_month;

-- Composição de MyTag por playlist: quais tags mais aparecem em cada uma, útil pra
-- entender o "clima" predominante de uma playlist sem precisar reouvir tudo.
-- HAVING count(*) >= 3 corta ruído de tags citadas 1-2 vezes só.
SELECT p.playlist_name, mv.value_name, count(*) AS faixas,
       round(100.0 * count(*) / (SELECT count(*) FROM track_playlist tp2 WHERE tp2.playlist_id = p.playlist_id), 1) AS pct_da_playlist
FROM playlists p
JOIN track_playlist tp ON tp.playlist_id = p.playlist_id
JOIN track_mytag tm ON tm.track_id = tp.track_id
JOIN mytag_values mv ON mv.value_id = tm.value_id
GROUP BY p.playlist_name, p.playlist_id, mv.value_name
HAVING count(*) >= 3
ORDER BY p.playlist_name, faixas DESC;

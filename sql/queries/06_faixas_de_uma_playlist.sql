-- Faixas de uma playlist, ordenadas por BPM -- ponto de partida pra montar a ordem
-- de um set. A leitura de pista em tempo real continua manual; isto só reduz o
-- espaço de busca.
SELECT t.track_id, t.name, t.artist, t.key_camelot, t.bpm, t.rating, t.play_count
FROM playlists p
JOIN track_playlist tp ON tp.playlist_id = p.playlist_id
JOIN tracks t ON t.track_id = tp.track_id
WHERE p.playlist_name = 'Afro House'  -- troque pelo nome da playlist
ORDER BY t.bpm, t.key_camelot;

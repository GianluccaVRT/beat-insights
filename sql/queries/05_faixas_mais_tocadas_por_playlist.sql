-- Top 3 faixas mais tocadas de cada playlist -- prioriza o que já foi validado em
-- pista na hora de decidir o que tocar de novo. play_count é acumulado sem
-- timestamp (decisão de escopo documentada em docs/spec.md): usado aqui como sinal
-- estático de "já validado", não como tendência ao longo do tempo.
WITH ranked AS (
    SELECT p.playlist_name, t.track_id, t.name, t.artist, t.play_count,
           RANK() OVER (PARTITION BY p.playlist_id ORDER BY t.play_count DESC) AS rnk
    FROM playlists p
    JOIN track_playlist tp ON tp.playlist_id = p.playlist_id
    JOIN tracks t ON t.track_id = tp.track_id
)
SELECT playlist_name, track_id, name, artist, play_count
FROM ranked
WHERE rnk <= 3 AND play_count > 0
ORDER BY playlist_name, rnk;

-- Top 3 faixas por gênero dentro de uma faixa de BPM (ex.: montar um bloco de set
-- num tempo específico), ranqueadas por rating e play_count via window function.
WITH ranked AS (
    SELECT t.*,
           RANK() OVER (PARTITION BY genre ORDER BY rating DESC, play_count DESC) AS rnk
    FROM tracks t
    WHERE bpm BETWEEN 120 AND 126  -- troque pela faixa de BPM desejada
)
SELECT genre, track_id, name, artist, key_camelot, bpm, rating, play_count
FROM ranked
WHERE rnk <= 3
ORDER BY genre, rnk;

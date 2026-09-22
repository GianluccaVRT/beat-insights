-- Faixas cujo rating manual destoa da média do próprio gênero (|z-score| >= 1.5) --
-- candidatas a revisão, mesma disciplina do TODO de "divergência rating x cluster"
-- do roadmap: sinaliza para revisão humana, nunca corrige automaticamente.
-- HAVING count(*) >= 10 evita z-score instável em gêneros com poucas faixas avaliadas.
WITH stats AS (
    SELECT genre, avg(rating) AS media, stddev(rating) AS desvio
    FROM tracks
    WHERE rating > 0
    GROUP BY genre
    HAVING count(*) >= 10 AND stddev(rating) > 0
)
SELECT t.track_id, t.name, t.artist, t.genre, t.rating,
       round(s.media, 2) AS media_genero,
       round((t.rating - s.media) / s.desvio, 2) AS z_score
FROM tracks t
JOIN stats s ON s.genre = t.genre
WHERE t.rating > 0 AND abs((t.rating - s.media) / s.desvio) >= 1.5
ORDER BY abs((t.rating - s.media) / s.desvio) DESC;

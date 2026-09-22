-- Compatibilidade harmônica (roda de Camelot) para uma faixa de referência, dentro
-- de uma tolerância de BPM de +-3. Regras clássicas de mixagem harmônica: mesma key,
-- key vizinha (+-1, mesma letra) e key relativa (mesmo número, letra oposta -- troca
-- entre maior/menor relativos).
WITH target AS (
    SELECT track_id, name, key_camelot, bpm,
           substring(key_camelot FROM '\d+')::int AS num,
           right(key_camelot, 1) AS letter
    FROM tracks
    WHERE name = '7A - 122 - GUIGO TESSEROLI - Caminho'  -- troque pelo nome da faixa alvo
    LIMIT 1
)
SELECT c.track_id, c.name, c.artist, c.key_camelot, c.bpm, c.rating,
       CASE
           WHEN c.key_camelot = t.key_camelot THEN 'mesma key'
           WHEN right(c.key_camelot, 1) = t.letter
                AND substring(c.key_camelot FROM '\d+')::int = ((t.num % 12) + 1) THEN 'vizinha (+1)'
           WHEN right(c.key_camelot, 1) = t.letter
                AND substring(c.key_camelot FROM '\d+')::int = (((t.num + 10) % 12) + 1) THEN 'vizinha (-1)'
           WHEN substring(c.key_camelot FROM '\d+')::int = t.num
                AND right(c.key_camelot, 1) != t.letter THEN 'relativa'
       END AS compatibilidade,
       abs(c.bpm - t.bpm) AS diff_bpm
FROM tracks c, target t
WHERE c.track_id != t.track_id
  AND abs(c.bpm - t.bpm) <= 3
  AND (
        c.key_camelot = t.key_camelot
        OR (right(c.key_camelot, 1) = t.letter AND substring(c.key_camelot FROM '\d+')::int = ((t.num % 12) + 1))
        OR (right(c.key_camelot, 1) = t.letter AND substring(c.key_camelot FROM '\d+')::int = (((t.num + 10) % 12) + 1))
        OR (substring(c.key_camelot FROM '\d+')::int = t.num AND right(c.key_camelot, 1) != t.letter)
  )
ORDER BY diff_bpm, compatibilidade;

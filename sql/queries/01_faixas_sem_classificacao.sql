-- Faixas sem nenhuma classificação (rating = 0 e sem MyTag), priorizadas por
-- play_count -- faixas já tocadas mas nunca avaliadas entram primeiro na fila de
-- revisão. Implementa o relatório do roadmap (Fase 2 do README).
SELECT t.track_id, t.name, t.artist, t.genre, t.play_count
FROM tracks t
LEFT JOIN track_mytag tm ON tm.track_id = t.track_id
WHERE t.rating = 0 AND tm.track_id IS NULL
ORDER BY t.play_count DESC, t.name;

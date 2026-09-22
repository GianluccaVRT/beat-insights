-- Crescimento da biblioteca por mês. date_added é a data de importação da faixa no
-- Rekordbox, não de execução -- diferente de play_count, tem timestamp real e pode
-- ser analisado no tempo sem violar a decisão de escopo sobre play_count
-- (documentada em docs/spec.md).
WITH monthly AS (
    SELECT date_trunc('month', date_added)::date AS mes, count(*) AS faixas_adicionadas
    FROM tracks
    GROUP BY mes
)
SELECT mes, faixas_adicionadas,
       sum(faixas_adicionadas) OVER (ORDER BY mes) AS total_acumulado
FROM monthly
ORDER BY mes;

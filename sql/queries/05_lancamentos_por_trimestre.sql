-- Pergunta de negócio: como o volume de lançamentos evolui trimestre a trimestre nos
-- últimos anos, e qual a taxa de crescimento (%) de um trimestre para o outro?
--
-- Filtro release_date_precision != 'year': agregação sub-anual (trimestre) -- mesma
-- razão da query 03 (álbuns com precisão 'year' cairiam todos artificialmente no Q1).
--
-- Window function: LAG() OVER (ORDER BY release_quarter) para taxa de crescimento
-- percentual trimestre a trimestre.
--
-- Uso de idx_albums_release_date: o filtro "release_date >= '2020-01-01'" cobre ~2,7%
-- da tabela albums (602 de 22.543 linhas) -- seletivo o suficiente para o otimizador
-- escolher Bitmap Index Scan em vez de Seq Scan. IMPORTANTE (achado real, não teórico):
-- testei primeiro com um corte mais amplo ("release_date >= '2015-01-01'", ~63% da
-- tabela) e o Postgres ignorou o índice e escolheu Seq Scan mesmo com ele presente --
-- índice existir não significa índice ser usado; o otimizador só compensa o Index Scan
-- quando o filtro é seletivo o bastante. Por isso a pergunta de negócio foi ajustada
-- para "últimos anos" em vez de "desde 2015".

SELECT
    release_quarter,
    n_tracks,
    ROUND(
        100.0 * (n_tracks - LAG(n_tracks) OVER (ORDER BY release_quarter))
        / NULLIF(LAG(n_tracks) OVER (ORDER BY release_quarter), 0),
        2
    ) AS growth_pct_vs_prev_quarter
FROM (
    SELECT
        DATE_TRUNC('quarter', al.release_date)::DATE AS release_quarter,
        COUNT(*) AS n_tracks
    FROM tracks t
    JOIN albums al ON al.album_id = t.album_id
    WHERE al.release_date >= '2020-01-01'
      AND al.release_date_precision != 'year'
    GROUP BY DATE_TRUNC('quarter', al.release_date)
) quarterly_counts
ORDER BY release_quarter;

-- =============================================================================
-- EXPLAIN ANALYZE -- COM idx_albums_release_date (estado padrão do schema)
-- =============================================================================
--  HashAggregate  (cost=1149.82..1161.84 rows=534 width=20) (actual time=5.337..5.338 rows=1 loops=1)
--    Group Key: date_trunc('quarter'::text, (al.release_date)::timestamp with time zone)
--    Batches: 1  Memory Usage: 49kB
--    ->  Hash Join  (cost=249.80..1146.29 rows=707 width=12) (actual time=0.438..5.260 rows=626 loops=1)
--          Hash Cond: ((t.album_id)::text = (al.album_id)::text)
--          ->  Seq Scan on tracks t  (cost=0.00..818.52 rows=28352 width=23) (actual time=0.003..1.903 rows=28352 loops=1)
--          ->  Hash  (cost=242.77..242.77 rows=562 width=27) (actual time=0.388..0.388 rows=602 loops=1)
--                Buckets: 1024  Batches: 1  Memory Usage: 43kB
--                ->  Bitmap Heap Scan on albums al  (cost=8.88..242.77 rows=562 width=27) (actual time=0.042..0.308 rows=602 loops=1)
--                      Recheck Cond: (release_date >= '2020-01-01'::date)
--                      Filter: ((release_date_precision)::text <> 'year'::text)
--                      Heap Blocks: exact=91
--                      ->  Bitmap Index Scan on idx_albums_release_date  (cost=0.00..8.73 rows=593 width=0) (actual time=0.024..0.024 rows=602 loops=1)
--                            Index Cond: (release_date >= '2020-01-01'::date)
--  Planning Time: 1.194 ms
--  Execution Time: 5.455 ms
--
-- =============================================================================
-- Passo de comparação: DROP INDEX idx_albums_release_date; -- executado, depois recriado
-- EXPLAIN ANALYZE -- SEM o índice (mesma query)
-- =============================================================================
--  HashAggregate  (cost=1470.20..1482.21 rows=534 width=20) (actual time=5.482..5.483 rows=1 loops=1)
--    Group Key: date_trunc('quarter'::text, (al.release_date)::timestamp with time zone)
--    Batches: 1  Memory Usage: 49kB
--    ->  Hash Join  (cost=570.17..1466.66 rows=707 width=12) (actual time=1.339..5.402 rows=626 loops=1)
--          Hash Cond: ((t.album_id)::text = (al.album_id)::text)
--          ->  Seq Scan on tracks t  (cost=0.00..818.52 rows=28352 width=23) (actual time=0.002..1.463 rows=28352 loops=1)
--          ->  Hash  (cost=563.14..563.14 rows=562 width=27) (actual time=1.298..1.298 rows=602 loops=1)
--                Buckets: 1024  Batches: 1  Memory Usage: 43kB
--                ->  Seq Scan on albums al  (cost=0.00..563.14 rows=562 width=27) (actual time=0.012..1.232 rows=602 loops=1)
--                      Filter: ((release_date >= '2020-01-01'::date) AND ((release_date_precision)::text <> 'year'::text))
--                      Rows Removed by Filter: 21941
--  Planning Time: 0.807 ms
--  Execution Time: 5.560 ms
--
-- Leitura: o custo estimado do sub-plano de albums cai de 563.14 (Seq Scan completo,
-- lendo as 22.543 linhas e descartando 21.941) para 242.77 (Bitmap Heap Scan lendo só
-- os 602 blocos relevantes via índice) -- quase metade do custo estimado. O tempo de
-- parede (5.455ms vs 5.560ms) é quase idêntico nessa escala (22k linhas cabem em
-- memória, a diferença fica dentro do ruído de medição) -- a vantagem real do índice
-- fica visível no CUSTO ESTIMADO e no ACCESS METHOD, e escalaria proporcionalmente ao
-- tamanho da tabela num dataset de produção maior que este portfólio.
-- CREATE INDEX idx_albums_release_date ON albums (release_date); -- recriado ao final
-- =============================================================================

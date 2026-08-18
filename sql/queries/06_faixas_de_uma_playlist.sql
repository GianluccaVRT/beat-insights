-- Pergunta de negócio: quais faixas (e seus artistas) pertencem a uma playlist
-- específica? Caso de uso direto de curadoria/comparação entre playlists de um mesmo
-- subgênero -- ex: "Big Room House | Festival Bangers", usada como exemplo abaixo.
--
-- Uso de idx_track_playlist_playlist_id: a PK composta de track_playlist é
-- (track_id, playlist_id) -- o índice dessa PK só serve de acesso eficiente pelo
-- prefixo esquerdo (track_id). Filtrar por playlist_id isolado (como aqui) exige o
-- índice extra criado especificamente para essa direção da consulta.

SELECT
    p.playlist_name,
    t.track_name,
    a.artist_name,
    t.popularity
FROM track_playlist tp
JOIN tracks t ON t.track_id = tp.track_id
JOIN artists a ON a.artist_id = t.artist_id
JOIN playlists p ON p.playlist_id = tp.playlist_id
WHERE tp.playlist_id = '5Bx5niVgi3qGQQw06C0RKq'  -- "Big Room House | Festival Bangers"
ORDER BY t.popularity DESC;

-- =============================================================================
-- EXPLAIN ANALYZE -- COM idx_track_playlist_playlist_id (estado padrão do schema)
-- =============================================================================
--  Sort  (cost=983.88..984.13 rows=102 width=55) (actual time=0.601..0.605 rows=100 loops=1)
--    Sort Key: t.popularity DESC
--    Sort Method: quicksort  Memory: 34kB
--    ->  Nested Loop  (cost=5.92..980.47 rows=102 width=55) (actual time=0.064..0.572 rows=100 loops=1)
--          ->  Index Scan using playlists_pkey on playlists p  (cost=0.27..8.29 rows=1 width=47) (actual time=0.010..0.010 rows=1 loops=1)
--                Index Cond: ((playlist_id)::text = '5Bx5niVgi3qGQQw06C0RKq'::text)
--          ->  Nested Loop  (cost=5.65..971.16 rows=102 width=54) (actual time=0.052..0.554 rows=100 loops=1)
--                ->  Nested Loop  (cost=5.37..938.95 rows=102 width=47) (actual time=0.044..0.445 rows=100 loops=1)
--                      ->  Bitmap Heap Scan on track_playlist tp  (cost=5.08..215.84 rows=102 width=46) (actual time=0.027..0.034 rows=100 loops=1)
--                            Recheck Cond: ((playlist_id)::text = '5Bx5niVgi3qGQQw06C0RKq'::text)
--                            Heap Blocks: exact=2
--                            ->  Bitmap Index Scan on idx_track_playlist_playlist_id  (cost=0.00..5.05 rows=102 width=0) (actual time=0.017..0.017 rows=100 loops=1)
--                                  Index Cond: ((playlist_id)::text = '5Bx5niVgi3qGQQw06C0RKq'::text)
--                      ->  Index Scan using tracks_pkey on tracks t  (cost=0.29..7.09 rows=1 width=47) (actual time=0.004..0.004 rows=1 loops=100)
--                            Index Cond: ((track_id)::text = (tp.track_id)::text)
--                ->  Index Scan using artists_pkey on artists a  (cost=0.29..0.32 rows=1 width=15) (actual time=0.001..0.001 rows=1 loops=100)
--                      Index Cond: (artist_id = t.artist_id)
--  Planning Time: 1.560 ms
--  Execution Time: 0.676 ms
--
-- =============================================================================
-- Passo de comparação: DROP INDEX idx_track_playlist_playlist_id; -- executado, depois recriado
-- EXPLAIN ANALYZE -- SEM o índice (mesma query)
-- =============================================================================
--  Sort  (cost=1473.11..1473.36 rows=102 width=55) (actual time=2.313..2.317 rows=100 loops=1)
--    Sort Key: t.popularity DESC
--    Sort Method: quicksort  Memory: 34kB
--    ->  Nested Loop  (cost=0.84..1469.70 rows=102 width=55) (actual time=1.570..2.272 rows=100 loops=1)
--          ->  Index Scan using playlists_pkey on playlists p  (cost=0.27..8.29 rows=1 width=47) (actual time=0.012..0.012 rows=1 loops=1)
--                Index Cond: ((playlist_id)::text = '5Bx5niVgi3qGQQw06C0RKq'::text)
--          ->  Nested Loop  (cost=0.57..1460.39 rows=102 width=54) (actual time=1.557..2.251 rows=100 loops=1)
--                ->  Nested Loop  (cost=0.29..1428.19 rows=102 width=47) (actual time=1.549..2.126 rows=100 loops=1)
--                      ->  Seq Scan on track_playlist tp  (cost=0.00..705.08 rows=102 width=46) (actual time=1.535..1.756 rows=100 loops=1)
--                            Filter: ((playlist_id)::text = '5Bx5niVgi3qGQQw06C0RKq'::text)
--                            Rows Removed by Filter: 32146
--                      ->  Index Scan using tracks_pkey on tracks t  (cost=0.29..7.09 rows=1 width=47) (actual time=0.003..0.003 rows=1 loops=100)
--                            Index Cond: ((track_id)::text = (tp.track_id)::text)
--                ->  Index Scan using artists_pkey on artists a  (cost=0.29..0.32 rows=1 width=15) (actual time=0.001..0.001 rows=1 loops=100)
--                      Index Cond: (artist_id = t.artist_id)
--  Planning Time: 1.471 ms
--  Execution Time: 2.374 ms
--
-- Leitura: sem o índice, o acesso a track_playlist vira Seq Scan varrendo as 32.246
-- linhas e descartando 32.146 pra achar as 100 da playlist (Rows Removed by Filter).
-- Com o índice, Bitmap Index Scan vai direto às linhas certas. Execution Time cai de
-- 2.374ms para 0.676ms -- ~3,5x mais rápido mesmo nesta escala pequena (32k linhas);
-- a vantagem tende a crescer com o tamanho da tabela em produção.
-- CREATE INDEX idx_track_playlist_playlist_id ON track_playlist (playlist_id); -- recriado ao final
-- =============================================================================

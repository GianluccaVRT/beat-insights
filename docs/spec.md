# Especificação Técnica — Projetos de Portfólio
**Gianlucca Tesseroli**

---

Projeto 1 — Pipeline de Dados + SQL Analítico + Dashboard

Alvo principal: Data Analyst / Data Scientist Alvo secundário: Software/AI Engineer (mostra domínio de dados de ponta a ponta)

Objetivo

Demonstrar SQL de nível sênior, Python para ETL e storytelling de dados.

Dataset definido

"30000 Spotify Songs" (Kaggle: joebeachcapital/30000-spotify-songs, originado do dataset TidyTuesday).

Por que esse dataset resolve o problema:

Audio features completas: danceability, energy, loudness, valence, tempo, acousticness, instrumentalness, speechiness, liveness
track_album_release_date — dimensão temporal, necessária para as window functions (tendência, moving average, crescimento por período)
playlist_genre (6 categorias, incluindo edm) e playlist_subgenre (inclui progressive electro house, electro house, big room, pop edm) — permite isolar o recorte de música eletrônica, conectando com sua identidade de DJ/produtor
~30.000 linhas, fonte única e coerente (mesma coleta, mesmo schema — evita o problema de juntar CSVs de origens diferentes)

Colunas principais: track_id, track_name, track_artist, track_popularity, track_album_id, track_album_name, track_album_release_date, playlist_name, playlist_id, playlist_genre, playlist_subgenre, danceability, energy, key, loudness, mode, speechiness, acousticness, instrumentalness, liveness, valence, tempo, duration_ms.

Decisão técnica: track_artist como string única (sem split multi-artista). Checagem no CSV bruto (32.833 linhas): 854 linhas (2,6%) de track_artist contêm algum separador candidato a multi-artista (vírgula, ponto e vírgula, "feat.", "&", "with"), mas a inspeção manual dos valores únicos mostrou que a maioria é falso positivo — o separador faz parte do nome do ato, não indica dois artistas (ex: "Dimitri Vegas & Like Mike", "Tyler, The Creator", "Sleeping With Sirens" são nomes de duo/banda únicos). Apenas o separador "feat." se mostrou confiável (~11 linhas, 0,03% do total, colaboração genuína). Dado que o ganho de normalizar (tabela de junção track_artist N:N) cobriria menos de 0,1% das linhas e exigiria uma lista de exceções curada manualmente para não corromper nomes de duo/banda, optamos por manter track_artist como coluna única em vez de criar uma tabela de junção. Limitação conhecida: "top artistas" por popularidade/contagem subestima faixas com feature (o segundo artista de um "feat." fica embutido na string, não é contado separadamente).

Decisão técnica: albums.release_date_precision. Checagem do CSV bruto mostrou 3 granularidades em track_album_release_date: data completa (94,3%, 30.947 linhas), ano-mês (0,09%, 31 linhas) e só ano (5,65%, 1.855 linhas). Datas incompletas são preenchidas com dia/mês "01" para caber em uma coluna DATE, mas isso sozinho introduziria viés artificial em janeiro em qualquer agregação mensal, sem indicar que é artefato de imputação. Por isso a tabela albums ganhou a coluna release_date_precision ('day'|'month'|'year', VARCHAR+CHECK em vez de ENUM nativo, dado que são só 3 valores fixos), marcando a granularidade original -- queries de tendência mensal podem filtrar ou ponderar por essa coluna em vez de tratar toda linha como dado exato.

Nota sobre a Spotify API (contexto de decisão): o plano original previa enriquecer o dataset com uma captura ao vivo via Spotify API. Descobrimos que os endpoints de Audio Features, Audio Analysis, Recommendations e Related Artists foram descontinuados para apps novos desde novembro/2024, e que mudanças adicionais em fevereiro/2026 restringiram ainda mais o Developer Mode (exigência de conta Premium, quota estendida só para empresas com 250k+ usuários). Por isso, optamos por um dataset estático já coletado antes dessas restrições, em vez de depender de uma API em contração. Essa rota via API fica registrada como plano B em standby: caso o dataset estático se mostre insuficiente (ex: cobertura temporal até 2020), ainda é possível usar os endpoints que permanecem funcionais (Search, Get Track/Album/Artist individuais) para complementar metadados pontuais — não audio features, que seguem indisponíveis para apps novos.

Arquitetura
CSV (Kaggle, baixado manualmente) → data/raw/
   → Script Python de ingestão (pandas)
   → PostgreSQL (schema normalizado: tracks, albums, genre/subgenre, playlists)
   → Camada de queries SQL analíticas
   → Dashboard (Power BI ou Looker Studio, ou React + Recharts se quiser reforçar front)
Stack técnica
Python: pandas, requests (se houver API), psycopg2/SQLAlchemy
Banco: PostgreSQL (local via Docker)
SQL: CTEs, window functions (RANK, LAG/LEAD, moving averages), índices, EXPLAIN ANALYZE
Dashboard: Power BI Desktop (mais rápido de exibir) ou Looker Studio (mais fácil de compartilhar link público)
Infra: Docker Compose (Postgres + script), para rodar com um comando
Entregáveis
Repositório GitHub com docker-compose.yml, scripts de ingestão, pasta sql/ com queries comentadas
5-8 queries SQL respondendo perguntas de negócio reais (ex: "qual a tendência de X por trimestre", "top 10 outliers", "taxa de crescimento mês a mês")
Dashboard publicado (link público)
README com: pergunta de negócio, modelagem do schema (diagrama ER simples), decisões técnicas, prints do dashboard


Critério de "pronto"

Você conseguir explicar em entrevista, sem olhar o código, por que escolheu cada índice e o que cada window function resolve.

---

# Changelog

Formato livre, em português, seguindo a disciplina já usada nos commits e no
README deste projeto: o que mudou, os números obtidos, e onde estão os artefatos.
Datas no formato AAAA-MM-DD.

## [Não lançado] — 3 espaços de features + k-NN (em andamento)

Ver `docs/decisions/ADR-001-tres-espacos-e-knn.md` pro contexto completo da decisão.

### Etapa 0 — Preservar o histórico (2026-09-22)
- Tag git `baseline-v1-v2` criada no commit `b91c411` (estado antes desta fase).
- `results/baseline_2026-09/metrics.json`: todos os números do baseline
  (ingestão + clustering V1/V2/V3) recomputados e verificados nesta sessão —
  21/21 valores batem com o README, dentro da tolerância de arredondamento
  (script: `src/verify_baseline.py`, leitura apenas, não escreve no banco).
- PNGs de `reports/cluster_v{1,2,3}_pca.png` copiados (não movidos) pra
  `results/baseline_2026-09/`.
- `docs/decisions/ADR-001-tres-espacos-e-knn.md` criado.
- Renomeação de apelido: V1 = espaço `meta`, V2 = espaço `meta_audio`,
  `audio` = espaço novo (era chamado "V3" antes desta fase).

## [Baseline 2026-09] — Fases 1–4 do projeto (2026-08-18 a 2026-09-22)

Estado congelado pela tag `baseline-v1-v2`. Resumo (números completos e fontes em
`results/baseline_2026-09/metrics.json` e `README.md`):

- **Ingestão** (`src/ingest.py`): merge dos exports Rekordbox (XML + TXT) por
  `(Name, Artist, DateAdded)`, filtro de escopo "All Tracks" — 1668 → 1649 faixas,
  13 playlists, 44 valores de MyTag (333 faixas com pelo menos 1 tag).
- **Clustering V1/`meta`** (`src/cluster_v1.py`): k=4, silhouette 0.368, 83 features
  (BPM, rating, gênero, MyTag one-hot).
- **Extração de áudio** (`src/extract_audio_features.py`, `librosa`): 1648/1649
  faixas processadas (28 features: tempo, spectral centroid, RMS, 13 MFCCs, 12
  chroma).
- **Clustering V2/`meta_audio`** (`src/cluster_v2.py`): k=4, silhouette 0.072, 111
  features, ARI vs. V1 = 0.019.
- **Clustering V3/`audio`** (`src/cluster_v3.py`): k=4, silhouette 0.080, 28
  features, ARI vs. `meta_audio` = 0.909, vs. `meta` = 0.009.
- **Explorador interativo** (`src/explorer.py`): dashboard Streamlit + Plotly,
  scatter 3D (PCA), filtros por gênero/MyTag/artista/faixa/BPM/rating, alterna
  entre os três modelos.
- **Assistente de set via LLM** (`src/set_assistant.py`): Ollama (`llama3.1:8b`)
  local + DuckDuckGo (`ddgs`), tool `query_library` sobre BPM/key Camelot/gênero/
  MyTag/cluster.

Commits relevantes: `d88b06f` (pivot pra biblioteca real), `174c0b8` (V1),
`acf823a` (V2), `7eeb692` (assistente LLM), `bea7807` (explorador 3D), `b91c411`
(V3, tag `baseline-v1-v2`).

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

### Etapa 1 — Auditoria de clustering nos 3 espaços (2026-09-22)
- `src/features.py`: módulo único de construção dos 3 espaços (`build_meta`,
  `build_meta_audio`, `build_audio`, `build_space`), consolidando a lógica antes
  duplicada em `cluster_v1.py`/`cluster_v2.py`/`cluster_v3.py`. Os três scripts
  viraram wrappers finos (mesma assinatura pública, sem quebrar `explorer.py`/
  `verify_baseline.py`). Regra única pra faixa sem áudio documentada e aplicada
  via `excluded_from_audio_spaces`.
- **Alteração de schema** (confirmada com o usuário antes de aplicar):
  `track_clusters.cluster_version` alargado de `VARCHAR(20)` pra `VARCHAR(40)` —
  os nomes de versão novos (ex. `meta_audio_k2_2026-09`, 22 caracteres) estouravam
  o limite antigo. `sql/schema/002_clustering.sql` atualizado.
- `src/audit_clustering.py`: varredura de k=2–20 (silhouette + inércia) por
  espaço, silhouette por cluster, PCA (3 componentes, variância explicada +
  top-8 loadings por componente), matriz de ARI entre todos os pares (3 espaços
  novos + os 3 rótulos históricos), teste das hipóteses H1–H3. Resultados em
  `results/etapa1_2026-09/` (ver `results/etapa1_2026-09/README.md` pro resumo).
- Rótulos novos persistidos em `track_clusters`, sem tocar nos históricos:
  `meta_k4_2026-09` (k=4, silhouette 0.3676 — idêntico a `v1_structured`, ARI=1.0),
  `meta_audio_k2_2026-09` (k=2, silhouette 0.1656),
  `audio_k2_2026-09` (k=2, silhouette 0.1867).
- **Achado**: ARI `meta_audio_k2` × `audio_k2` = **0.9903** (ainda mais alto que
  o 0.9085 do baseline em k=4) — reforça que o áudio domina o agrupamento dos
  espaços que o incluem.
- Hipóteses: H1 refutada (k=2 não é o melhor em `meta`; k=4 é), H2 confirmada
  (PC1 de `meta` dominado por rating/MyTag), H3 confirmada (treinar `meta` só
  nas 333 faixas com tag muda substancialmente os clusters, ARI=0.0748).

### Etapa 2 — Busca k-NN, `src/similarity.py` (2026-09-22)
- `src/camelot.py`: roda de Camelot extraída de `set_assistant.py` pra módulo
  compartilhado (regra "não duplicar lógica") — `compatible_keys(key_camelot)`,
  mesma implementação/regex de antes. `set_assistant.py` atualizado pra
  importar daqui; comportamento idêntico, testado.
- `src/similarity.py`: `similar_tracks(engine, track_id, space, k=10,
  metric="cosine", bpm_tol=3, camelot=True, candidate_pool=200)` —
  `sklearn.neighbors.NearestNeighbors` (busca exata, `algorithm="brute"`).
  BPM e key Camelot são filtros duros aplicados **depois** da busca, sobre um
  pool de 200 candidatos — nunca entram na distância. Saída: track_id, nome,
  artista, similaridade, BPM, key, Δ spectral centroid e Δ RMS em relação à
  faixa de referência (None em `meta`, que não tem dado de áudio).
- Testado nos 3 espaços, com/sem filtros, métrica cosseno e euclidiana, espaço
  inválido e faixa sem áudio (mensagens de erro claras nos dois últimos casos).
- Limitação do espaço `meta` confirmada empiricamente (não só teórica): faixa
  sem MyTag testada teve só 7 valores de similaridade únicos entre os 10
  vizinhos mais próximos — empate real, como documentado no módulo.

### Etapa 3 — Avaliação do k-NN, `src/eval_similarity.py` (2026-09-22)
- Métrica: precision@10 por co-ocorrência em playlist, sobre **832 faixas**
  (50.5% da biblioteca) que estão em ≥1 playlist. Baselines: aleatório puro e
  "BPM+Camelot com ordem aleatória" (mesmos filtros duros do sistema real, sem
  o ranking por similaridade) — 20 sorteios, seed fixa (42+draw), por faixa.
- Grade: 3 espaços × 2 métricas (cosseno/euclidiana), com ablação com/sem
  chroma em `meta_audio`/`audio` — 10 configurações, resultados em
  `results/etapa3_2026-09/knn_eval.csv` (ver `results/etapa3_2026-09/README.md`
  pra leitura completa).
- **O sistema real bate os dois baselines em toda configuração** (baseline
  aleatório ~0.22, BPM+Camelot aleatório ~0.30) — o ranking por similaridade
  agrega valor sobre o filtro sozinho.
- **`meta` vence por larga margem (0.70) — viés esperado, documentado, não
  qualidade superior**: playlists desta biblioteca são majoritariamente
  organizadas por gênero (`Prog House` 504 faixas, `Afro House` 143), e `meta`
  inclui gênero como feature direta. `audio` (0.32–0.34) tem a menor
  precision@10 mas ainda bate os baselines — coerente com a Etapa 1 (áudio
  não "sabe" a qual playlist uma faixa pertence).
- Ablação de chroma: melhora levemente `meta_audio` (0.42→0.46 cosine),
  efeito pequeno e inconsistente entre métricas em `audio` puro —
  inconclusivo, não usado pra decidir remover chroma.

### Etapa 4 — Aba "Vizinhos" no explorer.py, com UMAP (2026-09-22)
- `src/explorer.py` reestruturado em duas abas (`st.tabs`): "Clusters" (conteúdo
  existente, sem mudança de comportamento) e "Vizinhos" (nova).
- Aba "Vizinhos": seletor de espaço (`meta`/`meta_audio`/`audio`), faixa de
  referência, k, métrica, tolerância de BPM (liga/desliga), filtro Camelot
  (liga/desliga) e projeção de fundo (UMAP padrão / PCA). Chama
  `similarity.similar_tracks` diretamente — mesma função usada pelo assistente
  de LLM (Etapa 5), sem duplicar lógica de busca.
- Projeção UMAP (`umap-learn`, `random_state=42`, `n_jobs=1`) em cache por
  espaço, junto com PCA 2D pra comparação; nota na interface avisando que PCA
  não preserva vizinhança local quando selecionado.
- Scatter: resto da biblioteca em cinza claro, linhas da faixa de referência
  até cada vizinho (hover mostra a similaridade), vizinhos em cor forte,
  referência destacada (estrela, maior, contorno escuro).
- Tabela de vizinhos com Δ brilho (spectral centroid) e Δ energia (RMS) com
  seta de direção (↑/↓); "n/a" no espaço `meta`, que não tem dado de áudio.
- Gráfico de comparação de perfil (referência vs. vizinho escolhido): valores
  z-score (desvio-padrão da média da biblioteca nesse espaço) — eixo único e
  comparável entre dimensões de escalas muito diferentes (BPM em dezenas,
  spectral centroid em milhares), em vez de misturar unidades num só gráfico.
- Testado no navegador (Chrome via automação): troca de aba, troca de espaço
  (`meta`→`audio`, recalcula UMAP e volta a mostrar menos de 10 vizinhos
  quando o filtro de BPM+Camelot é mais restritivo), alternância UMAP/PCA com
  o aviso aparecendo, tabela de deltas com valores reais (não `n/a`) em
  espaços com áudio, gráfico de comparação atualizando por vizinho selecionado.

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

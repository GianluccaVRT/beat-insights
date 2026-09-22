# Beat Insights

Ferramenta de catalogação e análise da biblioteca musical de um DJ/produtor, criada para apoiar — com dados — a decisão de qual faixa entra em seguida num set. A decisão em tempo real (ler a pista) continua sendo do DJ; o projeto existe para reduzir o espaço de busca e revelar relações entre faixas que não são óbvias só de memória.

## O problema

Ao montar ou tocar um set, um DJ leva em conta o horário do slot, a estética da festa, e quem toca antes/depois. Parte da escolha da próxima faixa é técnica (mixagem harmônica via roda de Camelot, BPM compatível), parte é feeling, e parte é encontrar elementos semelhantes entre faixas (groove, melodia). Esse projeto cataloga a biblioteca de forma estruturada para apoiar essas três técnicas, sem tentar substituir a leitura de pista em tempo real.

## Fontes de dados

O Rekordbox (software de gestão de biblioteca usado pelo autor) não expõe todos os dados relevantes por um único caminho — foram necessários dois exports diferentes, combinados:

| Export | Formato | O que fornece |
|---|---|---|
| Collection + Playlists | XML (`File > Export Collection in xml format`) | `PlayCount`, caminho do arquivo (`Location`), `TrackID`, estrutura de playlists (relação faixa↔playlist) |
| Playlist para TXT | TXT (UTF-16, tab-separated) | Valores de **MyTag** (tags multi-select definidas livremente no Rekordbox) |

**Por que os dois**: o MyTag — uma das classificações centrais do projeto — **não é exportado em nenhuma versão do XML do Rekordbox**, apenas no export em TXT. E o TXT, por sua vez, não traz `PlayCount`, caminho do arquivo, nem a estrutura de playlists. A junção dos dois é feita por `(Name, Artist, DateAdded)` — ver "Resultados obtidos" abaixo para por que o título sozinho não é suficiente.

### Escopo dos dados: "All Tracks" como fonte da verdade

O XML de `Collection` pode conter entradas que não são faixas de set — na biblioteca de referência, 19 delas eram loops de sample de produção e gravações de sets inteiros catalogadas por engano. A regra de escopo: **qualquer item presente na `Collection` mas ausente da playlist `All Tracks` é descartado da análise.** `All Tracks` é tratada como a fonte da verdade sobre o que conta como "faixa" no domínio deste projeto.

## Limitações conhecidas (documentadas, não escondidas)

- **MyTag não tem informação de grupo/categoria em nenhum export do Rekordbox** — apenas uma lista plana de valores por faixa, sem indicar a qual grupo cada valor pertence. Isso é uma limitação do produto, não do processo de extração.
- **Cobertura de MyTag é baixa: só 333 das 1649 faixas (20%) têm pelo menos uma tag.** Isso limita diretamente a qualidade do clustering V1 (ver "Resultados obtidos").
- **Sem análise temporal de play count.** O Rekordbox expõe `PlayCount` como um contador acumulado, sem timestamp por reprodução — não há como derivar "estilos mais tocados ao longo do tempo" com os dados disponíveis. `PlayCount` é usado como sinal estático (ex: para priorizar quais faixas revisar primeiro), não como série temporal.
- **1 faixa da Collection não tem arquivo de áudio localizável em disco** (`7A - 122 - GUIGO TESSEROLI - Caminho.mp3` — só sobrou a versão `.wav` gêmea). Fica de fora da extração de features de áudio e dos espaços `meta_audio`/`audio`.
- **Empate no espaço `meta` do k-NN, pras faixas sem MyTag.** ~80% das faixas (1316/1649) não têm nenhuma MyTag e ficam com o mesmo vetor de tags (tudo zero) — os "vizinhos mais próximos" tendem a ficar quase empatados entre si (testado: uma faixa sem tag teve só 7 valores de similaridade únicos entre os 10 vizinhos). `similar_tracks` é mais informativo pras 333 faixas com MyTag.
- **Viés conhecido na avaliação de precision@10 (k-NN) por co-ocorrência em playlist.** Playlists desta biblioteca são majoritariamente organizadas por gênero (`Prog House` 504 faixas, `Afro House` 143) — o espaço `meta`, que inclui gênero como feature direta, é estruturalmente favorecido por essa métrica. Ela mede "concorda com a curadoria de playlist do DJ", não "sinal acústico puro" (ver seção "3 espaços de features + k-NN" abaixo).
- **UMAP (aba Vizinhos do explorer) preserva vizinhança local, não distância global.** Dois pontos próximos no gráfico são de fato parecidos; a distância entre dois clusters distantes no gráfico não tem significado quantitativo confiável — só PCA (opção alternativa na mesma aba) tenta preservar variância global, com a troca inversa (não preserva vizinhança local).

## Estrutura do projeto

```
data/raw/            Exports do Rekordbox (Export_Playlists.xml, Playlists.txt) -- gitignored, dados pessoais
docs/decisions/       ADRs -- decisões de arquitetura com contexto, alternativas e consequências
  ADR-001-tres-espacos-e-knn.md
sql/schema/           DDL, aplicado em ordem
  001_create_tables.sql   tracks, playlists, track_playlist, mytag_values, track_mytag
  002_clustering.sql      track_clusters (labels, por versão: v1_structured/v2_audio/v3_audio_only + novas da Etapa 1)
  003_audio_features.sql  audio_features (tempo/spectral/RMS/MFCCs/chroma extraídos via librosa)
sql/queries/          Queries analíticas prontas (ver "O que cada query faz" abaixo)
src/
  ingest.py                Parsing + merge dos dois exports Rekordbox, aplica escopo "All Tracks", popula o schema
  features.py               Módulo único dos 3 espaços de features (meta/meta_audio/audio) -- usado por clustering e k-NN
  camelot.py                Roda de Camelot (compatibilidade de key), compartilhado entre query_library e similarity
  clustering_common.py     Utilitários compartilhados entre clusterings: conexão, escolha de k, persistência, plot PCA
  cluster_v1.py             Clustering k-means espaço 'meta' (wrapper fino em cima de features.py)
  extract_audio_features.py Extração de features de áudio via librosa, faixa a faixa, incremental/resumível
  cluster_v2.py             Clustering k-means espaço 'meta_audio', compara contra V1 (Adjusted Rand Index)
  cluster_v3.py             Clustering k-means espaço 'audio' (diagnóstico), compara contra V1 e V2
  cluster_classified.py     Reroda V1/V2/V3 só nas faixas já classificadas (rating>0 ou MyTag), compara com a base inteira via ARI
  similarity.py             Busca k-NN (similar_tracks) nos 3 espaços, com filtros duros de BPM/Camelot
  verify_baseline.py        Recomputa e verifica (só leitura) os números do baseline V1/V2/V3 + ingestão
  audit_clustering.py       Etapa 1: varredura de k, silhouette por cluster, PCA loadings, ARI, H1-H3
  eval_similarity.py        Etapa 3: avalia o k-NN via precision@10 por co-ocorrência em playlist
  explorer.py               Dashboard local (Streamlit), seletor "Clusters" / "Vizinhos" (k-NN + UMAP) no menu lateral
  set_assistant.py          Chat de terminal (Ollama local + DuckDuckGo), tools query_library/similar_tracks/web_search
reports/               Saída visual do clustering (PCA 2D por versão, baseline)
results/               Métricas/artefatos versionados por etapa (baseline_2026-09/, etapa1_2026-09/, etapa3_2026-09/, etapa5_2026-09/, clustering_classificado_2026-09/)
docker-compose.yml     Postgres local para desenvolvimento
requirements.txt       Dependências Python (pandas, scikit-learn, librosa, ollama, ddgs, streamlit, plotly, umap-learn, ...)
CHANGELOG.md           Histórico de mudanças por etapa, com números e arquivos de resultado
```

### O que cada query em `sql/queries/` faz

| Arquivo | Propósito |
|---|---|
| `01_faixas_sem_classificacao.sql` | Faixas sem rating e sem MyTag, priorizadas por play_count — implementa o TODO do roadmap original |
| `02_compatibilidade_harmonica.sql` | Dada uma faixa de referência, acha candidatas compatíveis via roda de Camelot (mesma/vizinha/relativa) + tolerância de BPM |
| `03_top_faixas_por_genero_e_bpm.sql` | Top 3 faixas por gênero dentro de uma faixa de BPM |
| `04_composicao_mytag_por_playlist.sql` | Quais MyTags predominam em cada playlist |
| `05_faixas_mais_tocadas_por_playlist.sql` | Top 3 mais tocadas por playlist (play_count como sinal estático) |
| `06_faixas_de_uma_playlist.sql` | Lista faixas de uma playlist ordenadas por BPM/key, ponto de partida pra montar um set |
| `07_outliers_rating_por_genero.sql` | Faixas cujo rating manual destoa da média do gênero (z-score) — sinaliza pra revisão, não corrige |
| `08_crescimento_biblioteca_por_mes.sql` | Crescimento da biblioteca por `date_added` (não por play count, que não tem timestamp) |

## O que o sistema faz — e resultados obtidos

### 1. Catalogação (`src/ingest.py`)

Combina os dois exports do Rekordbox num schema relacional único.

**Resultados, rodado contra a biblioteca real:**
- `Collection`: 1668 entradas → **1649 depois do filtro "All Tracks"** (19 excluídas: 8 loops de sample de produção + 11 gravações de sets/arquivos catalogados por engano).
- **A chave de merge `Name = Track Title` sozinha não é única**: 3 colisões reais na biblioteca (mesmo título, `TrackID`s diferentes — remixes/formatos distintos do mesmo release, e uma duplicata genuína de import). A chave composta `(Name, Artist, DateAdded)`, com `Artist` vazio normalizado antes de comparar, resolve os 3 casos e dá merge 1:1 exato (1649/1649, testado).
- Estrutura de playlists é **flat** (14 nós, nenhuma pasta) — 13 playlists de negócio + `All Tracks` (usada só como filtro de escopo, não persistida como playlist).
- `rating` do XML vem codificado (0/51/102/153/204/255) — decodificado via `rating_xml // 51`, validado contra o TXT.
- Estado final no banco: **1649 tracks, 13 playlists, 1134 vínculos track↔playlist, 44 valores únicos de MyTag, 1617 vínculos track↔tag (333 faixas com pelo menos 1 tag)**.

### 2. Clusterização (`cluster_v1.py`, `extract_audio_features.py`, `cluster_v2.py`, `cluster_v3.py`)

Agrupamento não supervisionado (k-means, k escolhido por silhouette score) em três versões, com a comparação entre elas reportada como parte da análise.

**V1 — só metadados estruturados** (BPM, rating, gênero, MyTag via one-hot, 83 features):
- k=4 escolhido (silhouette 0.368, bem acima dos demais k testados).
- Perfil dos clusters: um cluster de 1007 faixas (61% da base) com rating médio 0.0, um de 528 com rating médio 3.0, e dois menores (Trance de BPM alto, e um outlier de 2 faixas "DJ Tools").
- **Achado**: o cluster dominante parece separar mais por *ausência de rating/MyTag* do que por semelhança sonora real — em espaço one-hot esparso (a maioria das 1649 faixas não tem MyTag), distância euclidiana tende a agrupar por "tem vs não tem metadado", não por textura musical.

**Extração de áudio** (`extract_audio_features.py`, via `librosa`):
- Janela de 60s por faixa, offset de 15s (pula intros sem custo extra de decode — testado). Tempo detectado, spectral centroid, RMS energy, 13 MFCCs, 12 bins de chroma.
- **1648/1649 faixas processadas** (~2s/faixa) — 1 falha (arquivo ausente em disco, ver limitações).

**V2 — metadados + áudio** (111 features):
- k=4, mas **silhouette caiu pra 0.072** (vs. 0.368 do V1).
- **Adjusted Rand Index entre V1 e V2 = 0.019** — praticamente zero, os dois modelos discordam quase totalmente sobre o que é "parecido".
- **Conclusão**: isso confirma a hipótese do `docs/spec.md` de que metadado categórico sozinho não captura similaridade sonora real — o áudio introduz uma noção de semelhança tímbrica contínua e bem menos separável em blocos nítidos que a estrutura esparsa do one-hot do V1. Não é "o V2 deu errado"; é evidência de que o V1 media principalmente completude de metadado, não som.

**V3 — só áudio, diagnóstico** (28 features: tempo, spectral centroid, RMS, 13 MFCCs, 12 chroma; sem BPM/rating/gênero/MyTag na matriz):
- k=4, silhouette 0.080 (na mesma faixa baixa do V2).
- **Adjusted Rand Index V3 × V2 = 0.909** (quase idêntico) e **V3 × V1 = 0.009** (quase aleatório).
- **Conclusão, respondendo à pergunta que o V3 foi criado pra responder**: o áudio sozinho já produz praticamente o mesmo agrupamento que metadados+áudio (V2) — o metadado contribui muito pouco pro resultado do V2 quando o áudio está presente. Em outras palavras, a similaridade "descoberta" pelo V2 é essencialmente similaridade de áudio; o V1 mede outra coisa inteiramente (completude de metadado), daí o ARI V1×V2 ≈ 0 já visto antes bater com V1×V3 ≈ 0 também.

Visualizações estáticas em `reports/cluster_v1_pca.png`, `reports/cluster_v2_pca.png` e `reports/cluster_v3_pca.png` (projeção PCA 2D) — ver também o explorador interativo abaixo (agora com V1/V2/V3).

**Clustering restrito a faixas classificadas** (`cluster_classified.py`, resultados em `results/clustering_classificado_2026-09/summary.json`):

Pergunta motivada pelo achado do V1 acima: será que o cluster dominante (61%, ausência de rating/MyTag) é um artefato de "tem vs. não tem metadado", ou o problema persiste mesmo isolando só as faixas já avaliadas? Reroda k-means nos três espaços, restrito às **581/1649 faixas classificadas (35%, rating > 0 ou MyTag)**, com os labels persistidos sob `cluster_version` própria (sufixo `_classified`), sem sobrescrever V1/V2/V3 completos:

| Espaço | Silhouette (base inteira) | Silhouette (só classificadas) | ARI vs. base inteira |
|---|---|---|---|
| `meta` (V1) | 0.368 | **0.126** | **0.0425** |
| `meta_audio` (V2) | 0.072 | 0.078 | 0.41 |
| `audio` (V3) | 0.080 | 0.101 | 0.66 |

- **V1 confirma o achado por eliminação**: restrito às faixas classificadas, o cluster dominante de 1007 faixas *desaparece* — os 4 clusters ficam em 20–205 faixas, todos com rating médio entre 1.8 e 3.8 (antes: um cluster de 61% com rating médio 0.0). Mas o silhouette **cai** de 0.368 pra 0.126, e o ARI contra o V1 completo é quase zero (0.0425) — ou seja, o silhouette alto do V1 original vinha majoritariamente de separar "tem metadado" de "não tem", não de agrupar por semelhança musical real dentro de quem já foi avaliado.
- **V2 e V3 mal mudam**: silhouette praticamente igual (0.072→0.078, 0.080→0.101) e ARI moderado/alto (0.41, 0.66) — os espaços com áudio já não dependiam do artefato de metadado ausente, então restringir a população não muda o quadro qualitativo.
- Reaproveita `src/features.py`/`src/clustering_common.py` — mesma lógica de `cluster_v1/v2/v3.py`, só filtrando a população de tracks/audio antes de montar a matriz de cada espaço.

### 3. Explorador interativo de clusters (`src/explorer.py`)

Antes de definir regras de classificação de faixas (próxima fase), dá pra olhar onde as faixas caem hoje nos três modelos e questionar visualmente se os clusters fazem sentido musical, em vez de decidir só pelos números agregados. Dashboard local via Streamlit:

```
streamlit run src/explorer.py
```

- Alterna entre os modelos V1 (metadados), V2 (metadados + áudio) e V3 (só áudio) já persistidos em `track_clusters` — recalcula só a projeção PCA (em 3D) pra plotar, não o clustering em si.
- Filtro de escopo **"Faixas incluídas na análise"** (Todas as tracks / Só tracks classificadas): a opção restrita troca pra clusters de fato recalculados nesse subconjunto (`cluster_classified.py`, ver seção anterior), não um filtro visual — o gráfico, o perfil por cluster e a tabela passam a refletir só as 581 faixas classificadas, com a caixa de contexto acima do gráfico mostrando os números reais (silhouette, ARI) de cada versão.
- Gráfico **3D** (`Scatter3d`, PCA com 3 componentes) com rotação/zoom interativos — eixos configuráveis: PCA 1/2/3, BPM, rating, play count, e (no V2/V3) tempo detectado/spectral centroid/RMS energy.
- Filtros: gênero, MyTag, busca por artista/faixa, faixa de BPM, faixa de rating.
- Cada ponto no gráfico tem tooltip com nome, artista, gênero, key, BPM, rating, play count e MyTag; tabela de perfil por cluster e tabela completa das faixas filtradas abaixo do gráfico.
- Paleta e codificação seguem o método do skill `dataviz` interno: cor categórica em ordem fixa (nunca ciclada) + símbolo por cluster como codificação secundária — testado com `scripts/validate_palette.js` do skill, que aponta que cor sozinha não é suficiente pra distinguir 4 clusters simultâneos num scatter (all-pairs); tabela em `st.dataframe` como visão alternativa sem depender de cor. `Scatter3d` do Plotly aceita um conjunto de símbolos bem menor que o `Scatter` 2D (sem `triangle-up`/`star`/etc.) — lista de símbolos própria pra 3D, mesma ordem fixa.

### 4. Assistente de set via LLM (`set_assistant.py`)

Chat que, dado um contexto de evento em texto livre, busca primeiro na base catalogada — `query_library` (filtra por BPM, key Camelot compatível, gênero, MyTag, cluster de som) ou `similar_tracks` (k-NN de verdade, Etapa 5 da fase "3 espaços + k-NN") — e só recorre a busca externa (`web_search`, via DuckDuckGo) se a base local não cobrir o pedido.

**Decisão de stack**: 100% local e gratuito — Ollama (`llama3.1:8b`) + `ddgs`, sem nenhuma API key paga, no lugar de Claude API/Tavily citados como exemplo no `docs/spec.md`. Prioriza reprodutibilidade sem custo sobre usar o modelo mais capaz disponível.

**`similar_tracks`: espaço padrão `meta`, justificado pela Etapa 3.** Entre os três espaços, `meta` teve a maior precision@10 (0.70) contra co-ocorrência real em playlist — ou seja, é o que melhor reproduz o que este DJ já considerou "combinar" o bastante pra colocar na mesma playlist, que é justamente o objetivo prático de um assistente de set. Ressalva repassada ao modelo via descrição da própria tool: isso é em parte porque `meta` inclui gênero como feature direta (viés já documentado nos "Resultados obtidos" da Etapa 3) — pra achar vizinhos sonoros fora do gênero da faixa de referência, a tool aceita `space='audio'`.

**Resultados, testado com pedidos reais** (ver `results/etapa5_2026-09/assistant_tests.md` pros 3 testes completos):
- A busca estruturada isolada é confiável: testada com "warmup pôr do sol, organic/afro house, 118-122 bpm" → achou 47 candidatas reais na base e sintetizou 3 sugestões corretas com key compatível.
- `similar_tracks` funcionou de primeira em 2 dos 3 testes, incluindo um caso em que o modelo **trocou sozinho pro espaço `audio`** ao ler no pedido "fora do gênero", seguindo a dica da descrição da tool.
- **Falha nova, documentada**: quando `similar_tracks` devolve um erro de nome ambíguo (`{"error": ..., "candidatas": [...]}`, pedindo pra especificar melhor), o modelo às vezes **não reconhece isso como um erro** — trata as candidatas de desambiguação como se fossem resultados de similaridade de verdade e inventa uma análise de compatibilidade sem sentido em cima delas, em vez de perguntar ao usuário qual faixa ele quis dizer. Padrão de falha diferente do já conhecido (narrar sem invocar a tool): aqui a tool roda certo, o problema é a síntese do modelo sobre um resultado de erro.
- 3 bugs de integração corrigidos ao testar contra o modelo real: valores-placeholder que o modelo manda em campos opcionais (`0`, `"None"`) sendo tratados como filtro válido; múltiplos gêneros separados por vírgula num filtro só (`"organic house, afro house"`); key Camelot inválida derrubando com `ValueError` cru em vez de erro tratável. Mais 1 bug corrigido no `similar_tracks`: `bpm_tol=None` não distinguia "não informado" (usar padrão 3) de "desligado de propósito" — corrigido com `bpm_tol<=0` como sentinela explícita de "sem filtro".
- **Limitação de classe de modelo, não bug**: a cadeia de 2 passos (tenta local → não acha → chama web_search) é instável no `llama3.1:8b` — às vezes ele narra "vou buscar na web" em texto solto sem de fato invocar a ferramenta, preenchendo a resposta com faixas fictícias. Um parser de recuperação (`_parse_pseudo_tool_call`) cobre o caso em que ele escreve a tool call como JSON em texto, mas não o caso em que só descreve a ação em prosa livre.

## Conclusões e próximos passos de melhoria

1. **A cobertura de MyTag (20%) é o maior gargalo de qualidade do clustering hoje.** Antes de investir mais em algoritmo, o maior ganho provável é classificar mais faixas — `sql/queries/01_faixas_sem_classificacao.sql` já prioriza isso por play_count (faixas tocadas e nunca avaliadas primeiro).
2. ✅ **Resolvido**: V1 mede completude de metadado mais do que som. O diagnóstico V3 (só áudio, sem metadados) confirmou: ARI V3×V2 = 0.909 (quase idêntico) e V3×V1 = 0.009 (quase aleatório) — o áudio já domina o resultado do V2 sozinho, o metadado contribui pouco quando o áudio está presente. Se o objetivo é "achar faixas parecidas" por som, V2 e V3 já respondem isso de forma praticamente equivalente; V1 mede outra coisa (completude de classificação manual).
3. **O TODO original do roadmap** ("sinalizar faixas cujo cluster diverge do rating manual") agora está desbloqueado — `track_clusters` já tem V1 e V2 persistidos; falta escrever o relatório que cruza cluster x rating (a query `07_outliers_rating_por_genero.sql` faz uma versão estatística disso por gênero, não por cluster ainda).
4. **O assistente de LLM funciona bem no caso de uso principal** (busca estruturada), mas se a confiabilidade da cadeia local→web virar prioridade, as opções já avaliadas nesta sessão são: um modelo local maior (ex. `qwen2.5:14b`) ou um tier gratuito de nuvem (Gemini/Groq) — ambos fora do escopo desta rodada por decisão explícita de manter 100% local nesta primeira versão.
5. **1 faixa (`track_id=210208753`) tem o arquivo referenciado pelo Rekordbox ausente em disco.** Vale uma checagem periódica de integridade Rekordbox↔arquivos, fora do escopo atual.
6. **Parser de nome de arquivo (regra `KEY - BPM - Artista - Título`) mencionado no `docs/spec.md` não foi implementado nesta rodada** — a ingestão foi direto dos exports Rekordbox, que já trazem `Name`, key e BPM estruturados; o parser continua útil só como fallback pra faixas ainda não catalogadas no Rekordbox.
7. **Implicação prática do achado do V3 pra próxima fase (classificação assistida)**: como V2 ≈ V3, o sinal de similaridade sonora vem quase todo do áudio — a fase de classificação pode se apoiar no cluster V3 (ou V2, equivalentes) como proxy de "soa parecido", em vez de tentar melhorar o encoding de metadado do V1 pra esse fim. Metadado continua útil pra filtro/negócio (gênero, MyTag, rating), só não pra medir semelhança sonora.
8. ✅ **Resolvido** (fase "3 espaços + k-NN", ver seção dedicada abaixo): substituiu clustering puro por k-NN como mecanismo principal de recomendação, com avaliação quantitativa real (precision@10) em vez de só métricas internas de cluster.
9. **Próximos passos mapeados, não implementados** (Etapa 6 da fase "3 espaços + k-NN", registrado aqui por decisão explícita de escopo): grafo de vizinhança (`pyvis` ou `streamlit-agraph`) visualizando as arestas k-NN da biblioteca inteira, e uma rota de transição A→B por caminho mínimo nesse grafo (série de faixas que conecta duas faixas específicas passo a passo, cada uma parecida com a próxima) — útil pra planejar a transição entre dois momentos de um set. Também em aberto: erro de síntese do assistente sobre resultado de tool ambíguo (ver "Assistente de set via LLM" acima) e testar um modelo local maior ou tier gratuito de nuvem pra confiabilidade de tool-calling encadeado (item 4).
10. ✅ **Resolvido**: `cluster_classified.py` confirma por eliminação o achado do V1 (item 2) — restrito só às 581 faixas classificadas, o cluster dominante de 61%/rating 0.0 desaparece, mas o silhouette do V1 *cai* de 0.368 pra 0.126 (ARI vs. V1 completo = 0.0425), enquanto V2/V3 mal mudam (ARI 0.41/0.66). Ou seja: o silhouette alto do V1 original media completude de metadado, não semelhança musical real — nem dentro do subconjunto já avaliado manualmente o espaço `meta` forma clusters nítidos por som. Reforça a recomendação do item 7 (apoiar a próxima fase de classificação assistida em `meta_audio`/`audio`, não em `meta`).

## 3 espaços de features + k-NN (2026-09)

Fase adicionada após o baseline V1/V2/V3, motivada pelo achado #2 acima (silhouette de k-means baixo em espaços com áudio, sinal de que a similaridade sonora é contínua, não organizada em blocos discretos). Substitui clustering puro por busca de vizinhos mais próximos (k-NN) como mecanismo principal de recomendação — os clusters continuam existindo, como visualização e filtro de "mood". Racional completo, alternativas consideradas e consequências em `docs/decisions/ADR-001-tres-espacos-e-knn.md`. Baseline anterior preservado intacto na tag git `baseline-v1-v2` e em `results/baseline_2026-09/` — nada das seções acima foi sobrescrito por esta fase.

### Correspondência de nomes

Os apelidos V1/V2/V3 usados nas seções acima continuam válidos; a partir desta fase, os mesmos três espaços de features também são chamados por um nome mais descritivo, usado no código (`src/features.py`, `src/similarity.py`) e nos resultados novos:

| Apelido histórico | Espaço (nome de código, a partir desta fase) | Conteúdo |
|---|---|---|
| V1 | `meta` | BPM, rating, gênero, MyTag (one-hot) — 83 features |
| V2 | `meta_audio` | `meta` + features de áudio padronizadas — 111 features |
| V3 | `audio` | só features de áudio padronizadas — 28 features |

### Histórico de decisões

1. **Dataset público (Kaggle) → biblioteca real do Rekordbox** — commit `d88b06f`. Ver `docs/spec.md`, "Contexto e Motivação".
2. **Claude API / Tavily (citados como exemplo no plano original) → Ollama local + DuckDuckGo**, 100% gratuito — Fase 4, commit `7eeb692`. Ver seção "Assistente de set via LLM" acima.
3. **[ADR-001](docs/decisions/ADR-001-tres-espacos-e-knn.md)** — manter os 3 espaços de features e adicionar k-NN como mecanismo principal de recomendação, em vez de só k-means. Commit `ec9f77c` em diante (tag `baseline-v1-v2` marca o estado imediatamente anterior).

### O que foi feito, etapa por etapa

| Etapa | O que entrega | Artefatos |
|---|---|---|
| 0 — Preservar histórico | Tag git + métricas do baseline recomputadas e verificadas (21/21 batem com o README) | `results/baseline_2026-09/` |
| 1 — Auditoria de clustering | Varredura de k=2–20 por espaço, silhouette por cluster, loadings de PCA, matriz de ARI completa, H1–H3 | `results/etapa1_2026-09/` |
| 2 — Busca k-NN | `src/similarity.py` (`NearestNeighbors` exato), `src/camelot.py` (módulo compartilhado) | `src/similarity.py`, `src/camelot.py` |
| 3 — Avaliação do k-NN | precision@10 por co-ocorrência em playlist, 3 espaços × 2 métricas × ablação de chroma, vs. 2 baselines | `results/etapa3_2026-09/` |
| 4 — Visualização | Aba "Vizinhos" no `explorer.py`: UMAP/PCA, faixa de referência destacada, tabela de deltas, comparação de perfil | `src/explorer.py` |
| 5 — Tool no assistente | `similar_tracks` exposta em `set_assistant.py`, testada com 3 pedidos reais | `results/etapa5_2026-09/assistant_tests.md` |

### Tabela de resultados

Formato: métrica \| espaço \| valor \| run \| arquivo \| script gerador. Linhas do baseline preservadas (não recalculadas nem sobrescritas) ao lado das novas desta fase.

| Métrica | Espaço | Valor | Run | Arquivo | Script gerador |
|---|---|---|---|---|---|
| silhouette (k, sweep 4–15) | `meta` | 0.368 (k=4) | baseline 2026-09 | `results/baseline_2026-09/metrics.json` | `cluster_v1.py` |
| silhouette (k, sweep 4–15) | `meta_audio` | 0.072 (k=4) | baseline 2026-09 | `results/baseline_2026-09/metrics.json` | `cluster_v2.py` |
| silhouette (k, sweep 4–15) | `audio` | 0.080 (k=4) | baseline 2026-09 | `results/baseline_2026-09/metrics.json` | `cluster_v3.py` |
| ARI | `meta` × `meta_audio` | 0.019 | baseline 2026-09 | `results/baseline_2026-09/metrics.json` | `cluster_v2.py` |
| ARI | `audio` × `meta_audio` | 0.909 | baseline 2026-09 | `results/baseline_2026-09/metrics.json` | `cluster_v3.py` |
| ARI | `audio` × `meta` | 0.009 | baseline 2026-09 | `results/baseline_2026-09/metrics.json` | `cluster_v3.py` |
| silhouette (k, sweep 2–20) | `meta` | 0.3676 (k=4, igual ao baseline) | etapa1_2026-09 | `results/etapa1_2026-09/summary.json` | `audit_clustering.py` |
| silhouette (k, sweep 2–20) | `meta_audio` | 0.1656 (k=2, diferente do baseline) | etapa1_2026-09 | `results/etapa1_2026-09/summary.json` | `audit_clustering.py` |
| silhouette (k, sweep 2–20) | `audio` | 0.1867 (k=2, diferente do baseline) | etapa1_2026-09 | `results/etapa1_2026-09/summary.json` | `audit_clustering.py` |
| ARI | `meta_k4` × `v1_structured` (baseline) | 1.0000 (idêntico — regression check do refactor) | etapa1_2026-09 | `results/etapa1_2026-09/ari_matrix_all.csv` | `audit_clustering.py` |
| ARI | `meta_audio_k2` × `audio_k2` | 0.9903 | etapa1_2026-09 | `results/etapa1_2026-09/ari_matrix_all.csv` | `audit_clustering.py` |
| H1 (k=2 é o melhor em `meta`?) | `meta` | refutada (melhor k=4) | etapa1_2026-09 | `results/etapa1_2026-09/hypotheses.json` | `audit_clustering.py` |
| H2 (PC1 de `meta` dominado por rating/MyTag?) | `meta` | confirmada (6/8 do top-8) | etapa1_2026-09 | `results/etapa1_2026-09/hypotheses.json` | `audit_clustering.py` |
| H3 (treinar só nas 333 c/ tag muda os clusters?) | `meta` | confirmada (ARI=0.0748) | etapa1_2026-09 | `results/etapa1_2026-09/hypotheses.json` | `audit_clustering.py` |
| precision@10 (cosine) | `meta` | **0.7041** | etapa3_2026-09 | `results/etapa3_2026-09/knn_eval.csv` | `eval_similarity.py` |
| precision@10 (cosine, c/ chroma) | `meta_audio` | 0.4166 | etapa3_2026-09 | `results/etapa3_2026-09/knn_eval.csv` | `eval_similarity.py` |
| precision@10 (cosine, s/ chroma) | `meta_audio` | 0.4602 | etapa3_2026-09 | `results/etapa3_2026-09/knn_eval.csv` | `eval_similarity.py` |
| precision@10 (cosine, c/ chroma) | `audio` | 0.3389 | etapa3_2026-09 | `results/etapa3_2026-09/knn_eval.csv` | `eval_similarity.py` |
| precision@10, baseline aleatório | todos | ~0.219–0.221 | etapa3_2026-09 | `results/etapa3_2026-09/knn_eval.csv` | `eval_similarity.py` |
| precision@10, baseline BPM+Camelot aleatório | todos | ~0.304–0.305 | etapa3_2026-09 | `results/etapa3_2026-09/knn_eval.csv` | `eval_similarity.py` |
| faixas avaliadas (≥1 playlist) | — | 832 de 1649 (50,5%) | etapa3_2026-09 | `results/etapa3_2026-09/summary.json` | `eval_similarity.py` |

Grade completa (10 configurações: 3 espaços × 2 métricas × ablação de chroma) em `results/etapa3_2026-09/knn_eval.csv`; leitura interpretativa completa em `results/etapa3_2026-09/README.md`.

### Achado principal desta fase

O k-NN confirma e aprofunda o achado do V3: **a similaridade sonora real é contínua** (silhouette baixo em `meta_audio`/`audio` mesmo variando k de 2 a 20 — nenhum k "resolve" isso), então k-NN (que não assume blocos discretos) é mais adequado que k-means como mecanismo de recomendação. Na avaliação por precision@10, `meta` vence por larga margem (0.70) — mas isso é o **viés esperado e documentado**, não qualidade superior: as playlists desta biblioteca são majoritariamente organizadas por gênero, que `meta` inclui como feature direta. `audio` (0.32–0.34) tem a menor precision@10 mas ainda bate os dois baselines em toda configuração — o ranking por similaridade agrega valor real, mesmo no espaço sem essa vantagem estrutural.

## Reprodutibilidade e privacidade

Os arquivos de áudio da biblioteca pessoal do autor **não** fazem parte do repositório (direitos autorais) — `data/raw/*` é gitignored. O que é público:
- O **código** de ingestão, clustering e assistente — qualquer pessoa com seus próprios exports do Rekordbox (ou um dataset de metadados equivalente) consegue rodar a pipeline completa.
- A stack roda sem nenhuma API paga: Postgres local via `docker-compose up -d`, extração de áudio via `librosa` (CPU), e o assistente via Ollama local. Ver "Como rodar" abaixo.

## Como rodar

### Pré-requisitos
- Python 3.12+, Docker (Postgres local) e Ollama (assistente de LLM) — tudo local, nada pago.
- Seus próprios exports do Rekordbox (`Export_Playlists.xml` e `Playlists.txt`) dentro de `data/raw/` — não vêm no repo (dados pessoais, gitignored). Sem eles dá pra ler o código, mas não pra rodar a pipeline contra dados reais.

### Setup inicial
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # edite POSTGRES_* se quiser trocar as credenciais padrão

docker compose up -d   # sobe o Postgres local (container beat-insights-db)

# aplica o schema, em ordem -- não há psql no host, roda dentro do container
docker compose exec -T postgres psql -U beat_insights -d beat_insights < sql/schema/001_create_tables.sql
docker compose exec -T postgres psql -U beat_insights -d beat_insights < sql/schema/002_clustering.sql
docker compose exec -T postgres psql -U beat_insights -d beat_insights < sql/schema/003_audio_features.sql
```

### Rodando cada fase (em ordem — cada uma depende dos dados da anterior)
```bash
python src/ingest.py                    # ingestão: popula tracks/playlists/mytag a partir dos exports
python src/cluster_v1.py                # clustering V1 (só metadados)
python src/extract_audio_features.py    # extração de áudio via librosa (~2s/faixa, resumível)
python src/cluster_v2.py                # clustering V2 (metadados + áudio), compara com V1
python src/cluster_v3.py                # clustering V3 (só áudio, diagnóstico), compara com V1 e V2
python src/cluster_classified.py        # reroda V1/V2/V3 só nas faixas classificadas, compara com a base inteira (ARI)

streamlit run src/explorer.py           # dashboard interativo -- abre em http://localhost:8501, seletor Clusters/Vizinhos no menu lateral

ollama pull llama3.1:8b                 # uma vez só, baixa o modelo (~5GB)
python src/set_assistant.py             # chat de terminal (query_library + similar_tracks + web_search)
```

### Fase "3 espaços de features + k-NN" (opcional, roda em cima dos dados acima)
```bash
python src/verify_baseline.py           # recomputa e verifica os números do baseline (só leitura, não escreve no banco)
python src/audit_clustering.py          # Etapa 1: varredura de k, PCA, ARI 3x3, H1-H3 -- persiste versões NOVAS em track_clusters
python src/eval_similarity.py           # Etapa 3: precision@10 do k-NN vs. baselines -- só leitura, não escreve no banco
```

### Como interromper com segurança
- **`set_assistant.py`**: digite `sair` (ou `exit`/`quit`), `Ctrl+D` ou `Ctrl+C` — não há estado persistido nesse chat, interromper a qualquer momento é seguro.
- **`streamlit run src/explorer.py`**: `Ctrl+C` no terminal onde está rodando (ou `pkill -f "streamlit run src/explorer.py"` se subiu em background). A tela só lê dados já persistidos no banco, nunca escreve — zero risco de corromper estado.
- **`extract_audio_features.py`**: seguro interromper a qualquer momento (`Ctrl+C`) — é o único script que grava uma faixa por vez em vez de em lote, propositalmente (ver docstring do arquivo), então o progresso feito fica salvo; rodar de novo pula as faixas já processadas.
- **`cluster_v1.py` / `cluster_v2.py` / `cluster_v3.py` / `cluster_classified.py` / `audit_clustering.py`**: idempotentes — `persist_clusters` (`clustering_common.py`) faz `DELETE` do `cluster_version` correspondente antes de inserir, então interromper e rodar de novo é seguro, sem duplicata (e nunca toca em `v1_structured`/`v2_audio`/`v3_audio_only`, que são versões diferentes).
- **`verify_baseline.py` / `eval_similarity.py`**: só leitura, nunca escrevem no banco — seguro interromper a qualquer momento.
- **`ingest.py`: NÃO é idempotente** — insere com `to_sql(if_exists="append")`, sem limpar as tabelas antes. Interromper no meio, ou rodar duas vezes sobre um banco já populado, falha com erro de chave duplicada (`track_id`/`playlist_name`/`value_name` são `UNIQUE`/`PK`) em vez de duplicar silenciosamente — falha alto, que é a propriedade de segurança que importa aqui (nenhuma tabela fica com dado incoerente sem avisar). Pra rodar de novo do zero: dropa as tabelas afetadas e reaplica o schema antes de rodar `ingest.py` de novo:
  ```bash
  docker compose exec -T postgres psql -U beat_insights -d beat_insights -c \
    "DROP TABLE IF EXISTS track_mytag, track_playlist, track_clusters, audio_features, mytag_values, tracks, playlists CASCADE;"
  docker compose exec -T postgres psql -U beat_insights -d beat_insights < sql/schema/001_create_tables.sql
  docker compose exec -T postgres psql -U beat_insights -d beat_insights < sql/schema/002_clustering.sql
  docker compose exec -T postgres psql -U beat_insights -d beat_insights < sql/schema/003_audio_features.sql
  ```
- **Postgres (`docker compose`)**: `docker compose stop` pausa o container sem apagar nada (o volume `pgdata` persiste). `docker compose down` para e remove o container, mas o volume nomeado continua existindo — os dados sobrevivem. **Nunca rode `docker compose down -v`** nem remova o volume `pgdata` sem querer apagar tudo — isso destrói o banco de verdade, incluindo o resultado de horas de ingestão/extração de áudio/clustering.
- **Ollama**: se subiu como serviço (`brew services start ollama`), `brew services stop ollama`. Se está em primeiro plano (`ollama serve`), `Ctrl+C`.

## Roadmap

1. ✅ **Ingestão de metadados** — merge dos exports XML + TXT, aplicação da regra de escopo (`All Tracks`), schema relacional inicial.
2. ✅ **Integração Rekordbox (leitura)** — coberta pela ingestão acima, com queries analíticas prontas. Relatório de divergência cluster×rating (item 3 das conclusões) ainda em aberto.
3. ✅ **Clusterização e visualização** — V1 estruturada, V2 com áudio, V3 só-áudio (diagnóstico), comparação entre as três (ver "Resultados obtidos").
3.5. ✅ **Explorador interativo de clusters** — dashboard local (`streamlit run src/explorer.py`), ponte antes de definir regras de classificação de faixas.
4. ✅ **Assistente de set via LLM** — busca na base local primeiro (`query_library` + `similar_tracks`, k-NN), busca externa como complemento, 100% local/gratuito.
5. ✅ **3 espaços de features + k-NN** (fase adicionada após o baseline, ver seção dedicada acima) — auditoria de clustering, busca k-NN, avaliação por precision@10, aba "Vizinhos" no explorer, tool no assistente. Etapa 6 (grafo de vizinhança + rota de transição) mapeada, não implementada (ver "Conclusões", item 9).
6. ⏳ **Classificação assistida de faixas** — próxima fase, ainda não iniciada. Deve se apoiar nos achados das conclusões acima (cobertura de MyTag como prioridade, espaços `meta_audio`/`audio` — equivalentes, ARI 0.909/0.9903 — como referência de similaridade sonora, k-NN em vez de clustering puro).

---
*Documento atualizado a partir dos resultados reais de cada fase, rodada contra a biblioteca Rekordbox do autor — não é mais só a especificação, é o que de fato aconteceu ao rodar o projeto.*

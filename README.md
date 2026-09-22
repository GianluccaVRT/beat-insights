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
- **1 faixa da Collection não tem arquivo de áudio localizável em disco** (`7A - 122 - GUIGO TESSEROLI - Caminho.mp3` — só sobrou a versão `.wav` gêmea). Fica de fora da extração de features de áudio (V2) e do clustering V2.

## Estrutura do projeto

```
data/raw/            Exports do Rekordbox (Export_Playlists.xml, Playlists.txt) -- gitignored, dados pessoais
sql/schema/           DDL, aplicado em ordem
  001_create_tables.sql   tracks, playlists, track_playlist, mytag_values, track_mytag
  002_clustering.sql      track_clusters (labels de k-means, por versão: v1_structured / v2_audio)
  003_audio_features.sql  audio_features (tempo/spectral/RMS/MFCCs/chroma extraídos via librosa)
sql/queries/          Queries analíticas prontas (ver "O que cada query faz" abaixo)
src/
  ingest.py                Parsing + merge dos dois exports Rekordbox, aplica escopo "All Tracks", popula o schema
  clustering_common.py     Utilitários compartilhados entre V1/V2: conexão, escolha de k (silhouette), persistência, plot PCA
  cluster_v1.py             Clustering k-means só com metadados estruturados (BPM, rating, gênero, MyTag one-hot)
  extract_audio_features.py Extração de features de áudio via librosa, faixa a faixa, incremental/resumível
  cluster_v2.py             Clustering k-means com metadados + áudio, compara contra V1 (Adjusted Rand Index)
  explorer.py               Dashboard local (Streamlit) pra explorar os clusters V1/V2 interativamente
  set_assistant.py          Chat de terminal (Ollama local + DuckDuckGo) que sugere faixas a partir de contexto de evento
reports/               Saída visual do clustering (PCA 2D por versão)
docker-compose.yml     Postgres local para desenvolvimento
requirements.txt       Dependências Python (pandas, scikit-learn, librosa, ollama, ddgs, streamlit, plotly, ...)
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

### 2. Clusterização (`cluster_v1.py`, `extract_audio_features.py`, `cluster_v2.py`)

Agrupamento não supervisionado (k-means, k escolhido por silhouette score) em duas etapas, com a comparação entre elas reportada como parte da análise.

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

Visualizações estáticas em `reports/cluster_v1_pca.png` e `reports/cluster_v2_pca.png` (projeção PCA 2D) — ver também o explorador interativo abaixo.

### 3. Explorador interativo de clusters (`src/explorer.py`)

Antes de definir regras de classificação de faixas (próxima fase), dá pra olhar onde as faixas caem hoje nos dois modelos e questionar visualmente se os clusters fazem sentido musical, em vez de decidir só pelos números agregados. Dashboard local via Streamlit:

```
streamlit run src/explorer.py
```

- Alterna entre os modelos V1 (metadados) e V2 (metadados + áudio) já persistidos em `track_clusters` — recalcula só a projeção PCA (agora em 3D) pra plotar, não o clustering em si.
- Gráfico **3D** (`Scatter3d`, PCA com 3 componentes) com rotação/zoom interativos — eixos configuráveis: PCA 1/2/3, BPM, rating, play count, e (no V2) tempo detectado/spectral centroid/RMS energy.
- Filtros: gênero, MyTag, busca por artista/faixa, faixa de BPM, faixa de rating.
- Cada ponto no gráfico tem tooltip com nome, artista, gênero, key, BPM, rating, play count e MyTag; tabela de perfil por cluster e tabela completa das faixas filtradas abaixo do gráfico.
- Paleta e codificação seguem o método do skill `dataviz` interno: cor categórica em ordem fixa (nunca ciclada) + símbolo por cluster como codificação secundária — testado com `scripts/validate_palette.js` do skill, que aponta que cor sozinha não é suficiente pra distinguir 4 clusters simultâneos num scatter (all-pairs); tabela em `st.dataframe` como visão alternativa sem depender de cor. `Scatter3d` do Plotly aceita um conjunto de símbolos bem menor que o `Scatter` 2D (sem `triangle-up`/`star`/etc.) — lista de símbolos própria pra 3D, mesma ordem fixa.

### 4. Assistente de set via LLM (`set_assistant.py`)

Chat que, dado um contexto de evento em texto livre, busca primeiro na base catalogada (`query_library`: filtra por BPM, key Camelot compatível, gênero, MyTag, cluster de som via `track_clusters`) e só recorre a busca externa (`web_search`, via DuckDuckGo) se a base local não cobrir o pedido.

**Decisão de stack**: 100% local e gratuito — Ollama (`llama3.1:8b`) + `ddgs`, sem nenhuma API key paga, no lugar de Claude API/Tavily citados como exemplo no `docs/spec.md`. Prioriza reprodutibilidade sem custo sobre usar o modelo mais capaz disponível.

**Resultados, testado com pedidos reais:**
- A busca estruturada isolada é confiável: testada com "warmup pôr do sol, organic/afro house, 118-122 bpm" → achou 47 candidatas reais na base e sintetizou 3 sugestões corretas com key compatível.
- 3 bugs de integração corrigidos ao testar contra o modelo real: valores-placeholder que o modelo manda em campos opcionais (`0`, `"None"`) sendo tratados como filtro válido; múltiplos gêneros separados por vírgula num filtro só (`"organic house, afro house"`); key Camelot inválida derrubando com `ValueError` cru em vez de erro tratável.
- **Limitação de classe de modelo, não bug**: a cadeia de 2 passos (tenta local → não acha → chama web_search) é instável no `llama3.1:8b` — às vezes ele narra "vou buscar na web" em texto solto sem de fato invocar a ferramenta, preenchendo a resposta com faixas fictícias. Um parser de recuperação (`_parse_pseudo_tool_call`) cobre o caso em que ele escreve a tool call como JSON em texto, mas não o caso em que só descreve a ação em prosa livre.

## Conclusões e próximos passos de melhoria

1. **A cobertura de MyTag (20%) é o maior gargalo de qualidade do clustering hoje.** Antes de investir mais em algoritmo, o maior ganho provável é classificar mais faixas — `sql/queries/01_faixas_sem_classificacao.sql` já prioriza isso por play_count (faixas tocadas e nunca avaliadas primeiro).
2. **V1 mede completude de metadado mais do que som.** Se o objetivo é usar clustering pra "achar faixas parecidas", o V2 (áudio) é a versão que deveria orientar essa decisão, não o V1 — vale considerar uma V3 só-áudio (sem metadados) como diagnóstico, pra isolar se o sinal de áudio sozinho forma clusters mais nítidos sem a diluição do one-hot esparso.
3. **O TODO original do roadmap** ("sinalizar faixas cujo cluster diverge do rating manual") agora está desbloqueado — `track_clusters` já tem V1 e V2 persistidos; falta escrever o relatório que cruza cluster x rating (a query `07_outliers_rating_por_genero.sql` faz uma versão estatística disso por gênero, não por cluster ainda).
4. **O assistente de LLM funciona bem no caso de uso principal** (busca estruturada), mas se a confiabilidade da cadeia local→web virar prioridade, as opções já avaliadas nesta sessão são: um modelo local maior (ex. `qwen2.5:14b`) ou um tier gratuito de nuvem (Gemini/Groq) — ambos fora do escopo desta rodada por decisão explícita de manter 100% local nesta primeira versão.
5. **1 faixa (`track_id=210208753`) tem o arquivo referenciado pelo Rekordbox ausente em disco.** Vale uma checagem periódica de integridade Rekordbox↔arquivos, fora do escopo atual.
6. **Parser de nome de arquivo (regra `KEY - BPM - Artista - Título`) mencionado no `docs/spec.md` não foi implementado nesta rodada** — a ingestão foi direto dos exports Rekordbox, que já trazem `Name`, key e BPM estruturados; o parser continua útil só como fallback pra faixas ainda não catalogadas no Rekordbox.

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

streamlit run src/explorer.py           # dashboard interativo -- abre em http://localhost:8501

ollama pull llama3.1:8b                 # uma vez só, baixa o modelo (~5GB)
python src/set_assistant.py             # chat de terminal
```

### Como interromper com segurança
- **`set_assistant.py`**: digite `sair` (ou `exit`/`quit`), `Ctrl+D` ou `Ctrl+C` — não há estado persistido nesse chat, interromper a qualquer momento é seguro.
- **`streamlit run src/explorer.py`**: `Ctrl+C` no terminal onde está rodando (ou `pkill -f "streamlit run src/explorer.py"` se subiu em background). A tela só lê dados já persistidos no banco, nunca escreve — zero risco de corromper estado.
- **`extract_audio_features.py`**: seguro interromper a qualquer momento (`Ctrl+C`) — é o único script que grava uma faixa por vez em vez de em lote, propositalmente (ver docstring do arquivo), então o progresso feito fica salvo; rodar de novo pula as faixas já processadas.
- **`cluster_v1.py` / `cluster_v2.py`**: idempotentes — `persist_clusters` (`clustering_common.py`) faz `DELETE` do `cluster_version` correspondente antes de inserir, então interromper e rodar de novo é seguro, sem duplicata.
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
3. ✅ **Clusterização e visualização** — V1 estruturada, V2 com áudio, comparação entre as duas (ver "Resultados obtidos").
3.5. ✅ **Explorador interativo de clusters** — dashboard local (`streamlit run src/explorer.py`), ponte antes de definir regras de classificação de faixas.
4. ✅ **Assistente de set via LLM** — busca na base local primeiro, busca externa como complemento, 100% local/gratuito.
5. ⏳ **Classificação assistida de faixas** — próxima fase, ainda não iniciada. Deve se apoiar nos achados das conclusões acima (cobertura de MyTag como prioridade, cluster V2 como referência de similaridade sonora).

---
*Documento atualizado a partir dos resultados reais de cada fase, rodada contra a biblioteca Rekordbox do autor — não é mais só a especificação, é o que de fato aconteceu ao rodar o projeto.*

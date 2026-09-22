# Contexto e Motivação

A versão anterior do Projeto 1 (`beat-insights`) usava um dataset público do Kaggle para demonstrar SQL analítico. Esta versão substitui o dataset genérico por um problema real do dia a dia de Guigo como DJ e produtor: **como organizar e classificar uma biblioteca de faixas de forma que a escolha da próxima track em um set — hoje feita "de ouvido", lendo a pista — seja apoiada por dados**, sem perder a decisão final em tempo real, que continua sendo do DJ.

O projeto ganha em autenticidade (é um problema com uso real, não um exercício acadêmico) e cobre tecnicamente o mesmo espectro que a versão anterior: ingestão e parsing de dados (Python), modelagem/armazenamento (SQL), aprendizado não supervisionado (clustering), e integração com LLM (AI Engineering) — mas agora com uma narrativa muito mais forte para entrevista.

## Técnicas de mixagem que o sistema precisa suportar (não substituir)

O sistema **não decide a próxima faixa por conta própria durante o set** — decisões em tempo real dependem de leitura de pista, algo que nenhum dado estático captura. O papel do sistema é **reduzir o espaço de busca e revelar relações não óbvias** entre faixas, apoiando três técnicas que Guigo já usa:

1. **Mixagem harmônica** (roda de Camelot: compatibilidade de key/escala)
2. **Feeling / conhecimento da faixa** (o sistema não substitui isso, mas os metadados de energia/mood ajudam a lembrar faixas esquecidas na biblioteca)
3. **Elemento semelhante/complementar** (groove de baixo, melodia) — esse é o mais difícil de capturar via metadado puro, e é a principal razão para considerar extração de features direto do áudio (ver seção de Clustering).

---

# Escopo e Dados

## Volume e formatos
- ~2.000 faixas atualmente, entre `.mp3`, `.wav`, `.aiff`/`.flac`
- O script de rename atual de Guigo funciona com `.mp3` mas falha em `.wav` — hipótese mais provável: arquivos `.wav` não têm um container de metadata padronizado como o ID3 do MP3 (o `.wav` usa chunks `LIST`/`INFO`, suportados de forma inconsistente entre bibliotecas Python e entre DAWs/lojas que geram o arquivo). Ação: revisar o script existente com a biblioteca `mutagen` (que trata WAV, mas com API diferente de MP3) antes de assumir que é um bug do script vs. limitação do arquivo.

## Convenção de nomenclatura (De → Para)

| Original | Convertido |
|---|---|
| `Kris - Submotion (Original Mix)` | `2A - 122 - Kris - Submotion` |
| `D-Nox - Agora (Extended Mix)` | `8B - 124 - D-Nox - Agora` |
| `GUIGO TESSEROLI, Adriatique - Depois (Artbat Extended Remix)` | `4B - 128 - GUIGO TESSEROLI, Adriatique - Depois (Artbat Remix)` |

**Regra de parsing inferida dos exemplos:**
```
{KEY} - {BPM} - {ARTISTA(S)} - {TÍTULO}[ ({REMIXER} Remix)]
```
- `KEY` e `BPM` vêm da página de compra (Beatport/Bandcamp), inseridos manualmente por Guigo — não extraídos do áudio.
- Sufixos genéricos (`Original Mix`, `Extended Mix`) são **removidos** do resultado final.
- Sufixos que indicam um remix nomeado são **mantidos**, mas normalizados: `"Artbat Extended Remix"` → `"Artbat Remix"` (remove "Extended", mantém o nome do remixer + "Remix").
- Múltiplos artistas permanecem separados por vírgula, sem alteração.

Essa regra cobre os 3 exemplos fornecidos; o parser deve ser construído com testes unitários a partir de uma amostra maior da biblioteca real antes de rodar em lote (casos como "VIP Mix", "Rework", "Edit", ou remixes com mais de um remixer podem exigir regras adicionais — a serem descobertas na prática, não assumidas agora).

## Parâmetros de classificação existentes

- **Rating (estrelas)**: escala 0–5. Quanto menor, menor a energia (faixa mais "plana", sem picos/vales de intensidade).
- **MyTag**: grupos de tags multi-select, sem taxonomia fixa — Guigo cria e ajusta os grupos livremente. Uma faixa pode ter múltiplas seleções dentro de um grupo, ou nenhuma.

---

# Fonte de Dados: Rekordbox (Confirmado com Exports Reais)

Os exports reais da biblioteca do autor (XML da Collection + Playlists, e TXT de playlist) foram analisados e validaram — e em um ponto, corrigiram — as premissas da versão anterior deste documento.

## Dois exports, combinados

| Export | Formato | O que fornece |
|---|---|---|
| Collection + Playlists | XML (`File > Export Collection in xml format`) | `PlayCount`, caminho do arquivo (`Location`), `TrackID`, estrutura de playlists (relação faixa↔playlist) |
| Playlist para TXT | TXT (UTF-16, tab-separated) | Valores de MyTag |

**Achado definitivo**: o MyTag **não existe em nenhuma ocorrência do XML** (confirmado por busca no arquivo inteiro da biblioteca de referência, ~1.668 faixas). Isso não é uma falha do export específico — é uma limitação do Rekordbox: MyTag só é acessível via o export em TXT, e mesmo ali, sem indicar a qual grupo cada valor pertence (apenas uma lista plana separada por `/`). Os dois exports são, portanto, complementares e obrigatórios — nenhum sozinho é suficiente.

**Chave de junção**: `Track Title` (TXT) e `Name` (XML) são idênticos — validado com 100% de correspondência exata (1.646/1.646 títulos únicos) na biblioteca de referência.

## Escopo dos dados: "All Tracks" como fonte da verdade

O nó `Collection` do XML pode conter entradas que não são faixas de set. Na biblioteca de referência, a `Collection` tinha 1.668 entradas contra 1.649 na playlist `All Tracks` — a diferença de 19 eram loops de sample de produção (`House 1`, `Breaks 1` etc.) e gravações de sets inteiros catalogadas por engano (arquivos como `RENTZ B2B GUIGO fix`, que são um set completo, não uma faixa).

**Regra de escopo definida**: `All Tracks` é a fonte da verdade sobre o que conta como "faixa" neste projeto. Qualquer item presente na `Collection` mas ausente de `All Tracks` é excluído da análise — na prática, a lógica de ingestão faz o merge dos dois exports e depois filtra pelo conjunto de `TrackID` que aparece em `All Tracks`.

## PlayCount: confirmado, mas sem análise temporal

`PlayCount` existe e tem dado real (1.013 de 1.668 faixas já tocadas, máximo de 14 plays na biblioteca de referência). Porém, é um contador acumulado — não há timestamp por reprodução em nenhum export do Rekordbox. **Decisão de escopo**: `PlayCount` é usado como sinal estático (ex: priorizar quais faixas sem classificação revisar primeiro, no TODO da Fase 2), mas nenhuma análise de "tendência ao longo do tempo" faz parte deste projeto — a métrica que a versão anterior deste documento cogitava não é viável com os dados disponíveis, e essa limitação é aceita, não contornada.

## Escopo desta fase: somente leitura

A integração inicial é **read-only**: o sistema lê o XML exportado e cruza com os metadados dos arquivos locais. Nenhuma escrita de volta ao Rekordbox está no escopo agora.

### TODO documentado (próxima fase, fora do MVP)
Análise de faixas **sem classificação** (sem MyTag, sem rating) e **sugestão de correção** em faixas já classificadas (ex: uma faixa com rating 5 mas com features de áudio muito próximas de faixas rating 2 — possível inconsistência de julgamento humano, não necessariamente um erro, mas digno de revisão).

Sugestão de implementação futura: um relatório periódico (script standalone, não precisa de UI) que:
1. Lista faixas sem nenhuma tag/rating, ordenadas por play count (faixas tocadas mas nunca classificadas são a prioridade)
2. Roda o modelo de clustering (já treinado na fase anterior) e sinaliza faixas cujo cluster diverge do rating atribuído manualmente, para revisão humana — nunca uma correção automática.

---

# Modelagem de Dados

Diferente da versão anterior (dataset público), aqui os dados têm duas origens que precisam ser conciliadas: **arquivo local** (metadata + nome do arquivo já parseado) e **Rekordbox** (play count, rating, MyTag, possível fallback de gênero/artista).

## Schema proposto (revisão inicial — sujeito a ajuste após o primeiro export real)

> **Nota**: o schema abaixo é o draft pré-implementação, mantido por valor histórico. O
> schema final ficou mais simples em dois pontos, confirmados contra os exports reais —
> ver `sql/schema/001_create_tables.sql` e a ressalva na Fase 1 do Roadmap: (1) sem
> `mytag_groups` (MyTag é lista plana, sem grupo, em todo export do Rekordbox); (2)
> `track_id` é o `TrackID` nativo do Rekordbox (inteiro), não um hash de path/UUID.

```
tracks
  - track_id (PK, hash do caminho do arquivo ou UUID gerado)
  - file_path
  - key_camelot        -- extraído do nome do arquivo
  - bpm                -- extraído do nome do arquivo
  - artist
  - title
  - remix_name          -- nullable
  - format              -- mp3 / wav / aiff / flac
  - duration_seconds
  - rating              -- 0-5, do Rekordbox
  - play_count           -- do Rekordbox
  - source_of_genre      -- 'file_tag' | 'rekordbox' (rastreia o fallback)

mytag_groups
  - group_id (PK)
  - group_name           -- definido livremente por Guigo no Rekordbox

mytag_values
  - value_id (PK)
  - group_id (FK)
  - value_name

track_mytag  (N:N — mesmo padrão do track_playlist do projeto anterior)
  - track_id (FK)
  - value_id (FK)

audio_features  (populada na fase de clustering, ver seção seguinte)
  - track_id (FK, PK)
  - tempo_detected        -- do áudio, pode divergir do BPM informado pela loja
  - spectral_centroid_mean
  - rms_energy_mean
  - ... (demais features, definidas na fase de extração)
```

Esse desenho já antecipa o TODO de Rekordbox (a tabela `mytag_groups`/`mytag_values` existe justamente para permitir a análise de "faixas sem classificação" mencionada acima) e mantém a mesma disciplina de modelagem N:N do projeto anterior (`track_mytag`, análogo ao `track_playlist` do `beat-insights`).

---

# Clustering — Por Que Extrair Features do Áudio

Guigo pediu para eu explicar melhor essa parte, então vale se aprofundar antes de decidir o escopo.

## O problema de usar só metadado para k-means

K-means opera em um espaço geométrico contínuo — ele calcula distância euclidiana entre pontos. Gênero e MyTag são **categóricos**: não existe uma noção natural de "distância" entre "Progressive House" e "Organic House" sem antes convertê-los artificialmente em números (one-hot encoding), o que produz um espaço onde todas as categorias ficam equidistantes entre si — perdendo justamente a informação de similaridade que se quer capturar (ex: Organic House e Melodic House deveriam ser "mais próximos" entre si do que de Techno, mas one-hot não representa isso).

BPM e rating (estrelas) já são numéricos e utilizáveis diretamente, mas sozinhos são pobres — duas faixas podem ter o mesmo BPM e rating e soarem completamente diferentes.

## O que a extração de áudio (via `librosa`) adiciona

`librosa` é uma biblioteca Python para análise de sinal de áudio. As features mais relevantes para o seu caso:

- **Tempo detectado**: valida (ou contesta) o BPM informado pela loja — às vezes a loja arredonda ou erra a detecção.
- **Spectral centroid**: indica o "brilho" do som — útil para diferenciar faixas mais "escuras"/dubby de faixas mais "brilhantes"/melódicas, uma distinção comum em organic/progressive house.
- **RMS energy** (root mean square): proxy quantitativo para "energia" — pode ser comparado ao rating manual (0-5) para achar divergências (ver TODO do Rekordbox).
- **MFCCs (Mel-frequency cepstral coefficients)**: capturam timbre — a "textura" do som, ajudando a agrupar faixas com groove/instrumentação parecida, mesmo que gênero/BPM sejam diferentes. Este é o recurso técnico mais próximo de operacionalizar a técnica de mixagem por "elemento semelhante" que você descreveu (groove de baixo, melodia parecida).
- **Chroma features**: relacionadas a conteúdo harmônico/tonal — um complemento (não substituto) à key do Camelot já anotada manualmente.

## Recomendação de escopo

Incluir extração de áudio **é recomendado**, mas como uma segunda etapa do clustering, não pré-requisito do MVP:
1. **V1 do clustering**: k-means só com features estruturadas (BPM, rating, MyTag via one-hot, gênero via one-hot) — rápido de implementar, já gera visualização útil.
2. **V2**: adicionar as features de áudio via `librosa` (processamento mais pesado — extrair de 2.000 arquivos leva minutos a dezenas de minutos, dependendo do hardware) e comparar se os clusters mudam de forma significativa. Essa comparação em si (V1 vs. V2) é um ótimo ponto de portfólio: mostra evolução iterativa e validação de hipótese, não só "rodei um modelo".

---

# Métricas ao Longo do Tempo — Fora de Escopo

Confirmado com os exports reais: o Rekordbox não segrega `PlayCount` por data em nenhum export (XML ou TXT) — apenas um contador acumulado por faixa. A métrica de "estilos mais tocados ao longo do tempo" **está fora do escopo deste projeto**, por decisão explícita, não por lacuna a resolver depois. Data de adição à pasta também não é utilizada como proxy (decisão de Guigo — não é uma informação relevante para o objetivo do projeto).

---

# Chat com LLM — Assistente de Set

## Comportamento esperado

Fluxo em duas etapas, na ordem:
1. **Buscar primeiro na base já catalogada** (tracks + clusters + classificações) — usando o prompt do usuário (ex: contexto do evento, line-up, horário do set) para filtrar/rankear candidatas dentro da biblioteca.
2. **Complementar com busca externa** somente se a base local não cobrir o pedido (ex: poucas faixas do "clima" pedido, ou pedido explícito de descobrir referências novas) — via busca web (mesmo padrão de ferramenta usado no projeto do case Indicium, ex: Tavily).

## Input do contexto do evento

Nesta fase, o input é **manual, via prompt de texto livre** (ex: "vou tocar na festa X, line-up: Y, Z; horário: pôr do sol; sugira uma linha de som"). Guigo observou que parte dessa informação só existe em posts do Instagram, difícil de extrair automaticamente — então essa automação fica fora de escopo por ora, e o usuário descreve o contexto manualmente.

## Grounding

O LLM deve ter acesso, via tool calling, a pelo menos:
- Query estruturada sobre a base de tracks (filtrando por cluster, key compatível via Camelot, faixa de BPM, MyTag)
- A busca externa (quando necessário), delimitada explicitamente para não substituir a base local por padrão.

---

# Reprodutibilidade e Portfólio Público

Decisão confirmada por Guigo: **os arquivos de áudio nunca vão para o repositório** (direitos autorais). O que vai:
- O **dataset de metadados** (informações públicas sobre as faixas: artista, título, BPM, key, classificações) — sem os arquivos de áudio em si.
- O código funciona em dois modos:
  - **Modo padrão**: opera sobre o dataset de metadados de Guigo (incluso no repo), permitindo que qualquer pessoa rode o projeto e veja resultados reais, sem precisar de biblioteca própria.
  - **Modo com biblioteca própria**: se o usuário apontar para sua própria pasta de música, o sistema roda a pipeline completa (parsing de nome de arquivo, extração de áudio) sobre os arquivos dele.

Essa dualidade também serve como prova de nível técnico para quem avaliar o repositório: dá pra ler o código e a lógica mesmo sem rodar com áudio real.

---

# Roadmap (MVP em 4 fases, ordem confirmada — todas implementadas)

## Fase 1 — Leitura de metadados + input de classificação — ⚠️ superada pela Fase 2
Planejada como parsing de nome de arquivo + tags ID3/`mutagen` locais, com schema
`mytag_groups`/`mytag_values` com grupo/categoria. **Não foi implementada como descrita
acima**: a ingestão real (`src/ingest.py`) foi direto pros exports do Rekordbox (Fase 2),
que já trazem `Name`, key, BPM e MyTag estruturados — tornando o parser de nome de arquivo
e a leitura de ID3 desnecessários nesta rodada. `mytag_groups` também não existe no schema
final: os exports reais confirmaram que o Rekordbox não expõe grupo/categoria pra MyTag em
nenhum export (ver seção "Fonte de Dados" acima), então a tabela de grupo do draft acima
viraria uma abstração sem dado real por trás — schema final é só `mytag_values`, lista
plana. O parser de nome de arquivo continua útil como fallback futuro, pra faixas ainda
não catalogadas no Rekordbox.

## Fase 2 — Integração Rekordbox ✅ implementada (virou a ingestão principal do projeto)
- Exportação XML + TXT (documentada no README).
- Parser + merge dos dois exports (`src/ingest.py`) — chave de merge real acabou sendo
  `(Name, Artist, DateAdded)`, não só `Name`/`Track Title` (ver README, "Resultados
  obtidos", pra por que título sozinho não é único).
- Relatório de faixas sem classificação: implementado como query SQL
  (`sql/queries/01_faixas_sem_classificacao.sql`), não como script Python standalone.

## Fase 3 — Clustering e Visualização ✅ implementada
- V1: k-means sobre features estruturadas (`src/cluster_v1.py`) — k=4, silhouette 0.368.
- V2: extração de áudio via `librosa` (`src/extract_audio_features.py`) + clustering (`src/cluster_v2.py`) — k=4, silhouette caiu para 0.072, Adjusted Rand Index vs. V1 = 0.019. Números completos e interpretação em `README.md`, seção "Resultados obtidos".
- **Visualização escolhida: dashboard interativo (não notebook)** — `src/explorer.py`, rodado via `streamlit run src/explorer.py`. Ponte entre "rodamos o clustering" e a próxima etapa de classificação assistida de faixas (ainda não iniciada): antes de propor regras de classificação, dá pra olhar visualmente onde as faixas caem hoje nos dois modelos. Alterna V1/V2, filtra por gênero/MyTag/artista/faixa/BPM/rating, e projeta em **3D** (`plotly.graph_objects.Scatter3d`, PCA com 3 componentes em vez de 2) com rotação e zoom interativos — decisão tomada porque um scatter 3D só se justifica quando a interação de orbitar é garantida (aqui é, nativa do Plotly dentro do Streamlit); um PNG 3D estático teria oclusão e perspectiva distorcendo distância sem ganho real sobre o 2D. Detalhes técnicos completos em `README.md`.

## Fase 4 — Chat com LLM ✅ implementada
- Tool calling sobre a base estruturada (query por cluster/key/BPM/MyTag) — `src/set_assistant.py`, tool `query_library`.
- Busca externa como complemento, não substituto — tool `web_search`.
- Input de contexto de evento via prompt manual — chat de terminal.
- **Mudança de stack vs. o planejado**: em vez de Claude API + Tavily (citados acima como exemplo), a implementação usa Ollama local (`llama3.1:8b`) + DuckDuckGo (`ddgs`, sem API key) — decisão pra manter a PoC 100% gratuita e reproduzível sem exigir nenhuma credencial paga. Trade-off e limitações reais (cadeia de 2 passos instável em modelo local pequeno) documentados no `README.md`.

---

# Pontos em Aberto

Resolvidos com os exports reais (ver seção "Fonte de Dados" acima): estrutura do MyTag no XML (não existe — confirmado), segregação de play count por data (não existe — métrica fora de escopo).

Ainda a validar na prática:
1. Casos de nomenclatura de arquivo além dos 3 exemplos fornecidos (VIP, Rework, Edit, múltiplos remixers)
2. Por que o script de rename atual falha especificamente em `.wav` (a confirmar revisando o script existente)
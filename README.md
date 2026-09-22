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

**Por que os dois**: o MyTag — uma das classificações centrais do projeto — **não é exportado em nenhuma versão do XML do Rekordbox**, apenas no export em TXT. E o TXT, por sua vez, não traz `PlayCount`, caminho do arquivo, nem a estrutura de playlists. A junção dos dois é feita pelo título da faixa (`Track Title` no TXT = `Name` no XML), validado com correspondência exata em 100% dos casos na biblioteca de referência usada no desenvolvimento.

### Escopo dos dados: "All Tracks" como fonte da verdade

O XML de `Collection` pode conter entradas que não são faixas de set — na biblioteca de referência, 19 delas eram loops de sample de produção e gravações de sets inteiros catalogadas por engano. A regra de escopo: **qualquer item presente na `Collection` mas ausente da playlist `All Tracks` é descartado da análise.** `All Tracks` é tratada como a fonte da verdade sobre o que conta como "faixa" no domínio deste projeto.

## Limitações conhecidas (documentadas, não escondidas)

- **MyTag não tem informação de grupo/categoria em nenhum export do Rekordbox** — apenas uma lista plana de valores por faixa, sem indicar a qual grupo cada valor pertence. Isso é uma limitação do produto, não do processo de extração.
- **Sem análise temporal de play count.** O Rekordbox expõe `PlayCount` como um contador acumulado, sem timestamp por reprodução — não há como derivar "estilos mais tocados ao longo do tempo" com os dados disponíveis. `PlayCount` é usado como sinal estático (ex: para priorizar quais faixas revisar primeiro), não como série temporal.
- **Regras de nomenclatura de arquivo cobrem os casos observados até agora** (`KEY - BPM - Artista - Título`, com remixes nomeados preservados e sufixos genéricos como "Original Mix"/"Extended Mix" removidos); casos não previstos (VIP, Rework, Edit, múltiplos remixers) podem exigir ajuste do parser conforme aparecem na prática.

## O que o sistema faz

### 1. Catalogação
Combina os dois exports do Rekordbox num schema relacional único (faixas, playlists, tags, e a relação N:N faixa↔playlist), com leitura de metadados nativos do arquivo de áudio (ID3 e equivalentes) como fallback quando o dado não vier do Rekordbox.

### 2. Clusterização
Agrupamento não supervisionado (k-means) das faixas, em duas etapas:
- **V1** — apenas com metadados estruturados (BPM, rating, gênero, MyTag via one-hot encoding).
- **V2** — enriquecido com features extraídas diretamente do áudio via `librosa` (tempo detectado, spectral centroid, RMS energy, MFCCs, chroma). Metadados categóricos sozinhos não capturam bem noções de similaridade sonora (timbre, "groove"); as features de áudio aproximam o sistema da forma como um DJ realmente escuta semelhança entre faixas, além de servir para validar/contestar o BPM informado pela loja de música.

A comparação entre V1 e V2 é reportada como parte da análise — não só "rodamos um modelo", mas "o que mudou ao adicionar sinal de áudio".

### 3. Assistente de set via LLM
Um chat que, dado um contexto de evento descrito em texto livre (line-up, horário, estética), primeiro busca sugestões dentro da própria biblioteca já catalogada e só recorre a busca externa quando a base local não cobre o pedido.

## Reprodutibilidade e privacidade

Os arquivos de áudio da biblioteca pessoal do autor **não** fazem parte do repositório (direitos autorais). O que é público:
- O **dataset de metadados** (informações públicas sobre as faixas — artista, título, BPM, key, classificações), sem os arquivos de áudio.
- O projeto roda em dois modos: com o dataset de metadados incluso no repositório (permitindo que qualquer pessoa veja o funcionamento real, sem precisar de biblioteca própria), ou apontando para a biblioteca Rekordbox de quem estiver rodando.

## Roadmap

1. **Ingestão de metadados** — merge dos exports XML + TXT, aplicação da regra de escopo (`All Tracks`), parsing do nome de arquivo, schema relacional inicial.
2. **Integração Rekordbox** (leitura) — já coberta pela ingestão acima. Próxima etapa dentro desta fase: relatório de faixas sem classificação (sem MyTag, sem rating) e sinalização de possíveis inconsistências entre rating manual e cluster obtido, para revisão humana — nunca correção automática.
3. **Clusterização e visualização** — V1 estruturada, V2 com áudio, comparação entre as duas.
4. **Assistente de set via LLM** — busca na base local primeiro, busca externa como complemento.

---
*Documento gerado a partir da especificação técnica do projeto; reflete decisões já validadas contra os exports reais do Rekordbox do autor.*
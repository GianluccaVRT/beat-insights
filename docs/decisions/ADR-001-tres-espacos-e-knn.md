# ADR-001: Três espaços de features (meta/meta_audio/audio) + busca k-NN

- **Status**: aceita
- **Data**: 2026-09-22
- **Contexto do commit**: proposta a partir do estado `baseline-v1-v2` (tag git), commit `b91c411`

## Contexto

A Fase 3 do projeto (ver `README.md`, "Resultados obtidos") treinou três modelos de
k-means sobre três espaços de features diferentes da mesma biblioteca (1649 faixas
do Rekordbox, ver `docs/spec.md` pra como os dados foram obtidos):

| Apelido histórico | Espaço (nome usado a partir desta fase) | Conteúdo |
|---|---|---|
| V1 | `meta` | BPM, rating, gênero, MyTag (one-hot) — 83 features |
| V2 | `meta_audio` | `meta` + tempo/spectral centroid/RMS/MFCCs/chroma via `librosa` — 111 features |
| V3 | `audio` | só as 28 features de áudio, sem nenhum metadado |

Números do baseline, recomputados e verificados nesta sessão (script
`src/verify_baseline.py`, sem retreinar nenhum modelo — só lê os rótulos já
persistidos em `track_clusters`; ver `results/baseline_2026-09/metrics.json` pra
cada valor com sua fonte):

| Métrica | `meta` | `meta_audio` | `audio` |
|---|---|---|---|
| k (varredura 4–15, silhouette) | 4 | 4 | 4 |
| silhouette | 0.3676 | 0.0720 | 0.0803 |
| n features | 83 | 111 | 28 |
| n faixas | 1649 | 1648 | 1648 |

Adjusted Rand Index entre pares: `meta`×`meta_audio` = 0.0189; `audio`×`meta_audio`
= 0.9085; `audio`×`meta` = 0.0090.

**Diagnóstico**: `meta` tem o silhouette mais alto, mas por um motivo espúrio — o
cluster dominante (1007/1649, 61%) separa por *ausência* de rating/MyTag, não por
som (ver README). `audio` e `meta_audio` têm ARI de 0.9085 entre si: o áudio já
explica quase todo o agrupamento de `meta_audio` sozinho, o metadado contribui
pouco quando o áudio está presente. A similaridade sonora real parece **contínua**
(silhouette baixo em ambos os espaços com áudio), não organizada em blocos
discretos e nítidos — o que k-means, por natureza, tenta forçar.

## Decisão

1. Manter os três espaços (`meta`, `meta_audio`, `audio`) como visualização e
   filtro de "mood"/"vibe" — cada um continua útil pra esse fim, e os nomes V1/V2
   ficam como apelidos históricos documentados no README.
2. **Adicionar busca por vizinhos mais próximos (k-NN)** como mecanismo principal
   de recomendação de faixa (`src/similarity.py`, `sklearn.neighbors.NearestNeighbors`,
   busca exata). K-NN não assume que o espaço se organiza em blocos discretos —
   só usa distância local, que é exatamente o que os dados de áudio parecem ter
   (contínuo, sem fronteiras nítidas). BPM e key Camelot entram como **filtros
   duros** pós-busca, não como parte da métrica de distância.
3. Avaliar cada espaço tanto por clustering (silhouette, ARI, já feito) quanto por
   k-NN (precision@10 por co-ocorrência em playlist, Etapa 3), pra decidir qual
   espaço vira o padrão do assistente de set (`set_assistant.py`).

## Alternativas consideradas

- **Manter só k-means, sem k-NN**: rejeitada. O achado do V3 (ARI 0.9085 vs.
  `meta_audio`, silhouette baixo em ambos os espaços com áudio) é evidência de que
  a estrutura real é contínua — forçar blocos discretos com k-means esconde
  informação de similaridade útil (duas faixas podem ser muito parecidas e cair em
  clusters "vizinhos" diferentes, sem que k-means capture esse grau).
- **Descartar o espaço `meta`**: rejeitada. Mesmo com o problema de completude de
  metadado, `meta` ainda é o único espaço que enxerga gênero e MyTag diretamente —
  úteis como filtro de negócio (ex.: "só organic house"), mesmo que não meçam
  semelhança sonora de verdade. Mantido, com a limitação documentada.
- **Índice aproximado de vizinhança (ex.: FAISS, `pgvector` com HNSW/IVF) em vez de
  busca exata**: rejeitada por ora — 1649 faixas não justificam o custo de
  aproximação; `NearestNeighbors` exato do scikit-learn resolve em milissegundos
  nesse volume. `pgvector` fica registrado aqui como evolução possível se o volume
  da biblioteca crescer o suficiente pra justificar.

## Consequências

- `src/features.py` centraliza a construção dos três espaços (reaproveitando
  `cluster_v1.build_features`/`cluster_v2.build_features`/`cluster_v3.build_features`
  em vez de duplicar), usado tanto pelo clustering quanto pelo k-NN.
- Nenhum dado histórico é sobrescrito: os rótulos `v1_structured`/`v2_audio`/
  `v3_audio_only` em `track_clusters` continuam intactos; clusterizações novas desta
  fase (varredura k=2–20) usam versões novas (ex.: `meta_k<k>_2026-09`).
- `set_assistant.py` ganha uma tool `similar_tracks`, com o espaço padrão decidido
  pelo resultado da avaliação k-NN (Etapa 3), não escolhido a priori.
- Roda de Camelot deixa de estar só em `set_assistant.py` e vira módulo
  compartilhado, usado também pelo filtro duro do k-NN.

## Reprodutibilidade

- `random_state=42` fixado em tudo que é estocástico (KMeans já seguia essa
  convenção desde a Fase 3; UMAP e qualquer amostragem/baseline aleatório desta
  fase seguem o mesmo).
- Versões das libs no ambiente desta sessão (`python3 --version`, `pip show`):
  Python 3.12.6, pandas 3.0.5, numpy 2.5.2, scikit-learn 1.9.1, librosa 1.0.0,
  matplotlib 3.11.2, streamlit 1.64.0, plotly 7.1.0. `umap-learn` ainda não
  instalado no ambiente — será adicionado a `requirements.txt` na Etapa 4.

## Referências

- `results/baseline_2026-09/metrics.json` — todos os números citados acima, com o
  script que os gerou.
- `results/baseline_2026-09/cluster_v{1,2,3}_pca.png` — visualizações congeladas do
  estado pré-fase.
- `README.md`, seções "Resultados obtidos" e "Conclusões e próximos passos de
  melhoria" — histórico completo até este ADR.
- Tag git `baseline-v1-v2` — snapshot do código nesse estado.

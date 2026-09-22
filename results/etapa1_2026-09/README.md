# Etapa 1 — Auditoria de clustering nos 3 espaços

Gerado por `src/audit_clustering.py`. Ver `docs/decisions/ADR-001-tres-espacos-e-knn.md`
pro contexto da fase.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `k_sweep_<espaco>.csv` / `.png` | Silhouette e inércia pra k=2..20 |
| `silhouette_by_cluster_<espaco>.csv` | Silhouette médio/min/max por cluster, no k escolhido |
| `pca_loadings_<espaco>.csv` | Top-8 features por PC1-PC3 |
| `pca_variance.csv` | `explained_variance_ratio_` de PC1-PC3, todos os espaços |
| `ari_matrix_all.csv` | ARI entre todos os pares (3 espaços novos + 3 rótulos históricos) |
| `k_sweep_meta_only_tagged.csv` / `.png` | Varredura de k do experimento H3 (meta só nas 333 faixas com MyTag) |
| `hypotheses.json` | H1/H2/H3, resultado e números |
| `summary.json` | k escolhido, silhouette, n_features/n_faixas por espaço, `cluster_version` persistido |

## k escolhido por espaço (varredura 2–20, vs. varredura histórica 4–15)

| Espaço | k (Etapa 1, 2–20) | silhouette | k histórico (4–15) | silhouette histórico |
|---|---|---|---|---|
| `meta` | 4 | 0.3676 | 4 | 0.368 |
| `meta_audio` | **2** | 0.1656 | 4 | 0.072 |
| `audio` | **2** | 0.1867 | 4 | 0.080 |

`meta` escolheu o mesmo k tanto na varredura antiga (4–15) quanto na nova (2–20) —
ARI entre `meta_k4_2026-09` e `v1_structured` = **1.0000** (idêntico), o que também
serve de teste de regressão pro refactor de `cluster_v1.py` em cima de
`src/features.py`. Já `meta_audio` e `audio` preferem k=2 quando a varredura inclui
k baixo — silhouette mais alto que em k=4, mas ainda numa faixa baixa (0.17–0.19),
consistente com a leitura de que a similaridade de áudio é contínua, não organizada
em blocos nítidos (nenhum k "resolve" isso).

## ARI — achado principal desta etapa

`meta_audio_k2_2026-09` × `audio_k2_2026-09` = **0.9903** — ainda mais alto que o
0.9085 (V2×V3, k=4) já visto no baseline. Em k=2, a divisão de `meta_audio` é
praticamente idêntica à de `audio` puro — reforça o achado do baseline: o áudio
domina o resultado dos espaços que o incluem, o metadado contribui pouco.
`meta_k4_2026-09` × qualquer espaço com áudio: ARI ≈ 0 (chegando a levemente
negativo) — `meta` mede outra coisa, sem relação com o agrupamento por som.

## Hipóteses

- **H1 (REFUTADA)**: k=2 não é o melhor k em `meta` — k=4 tem silhouette maior
  (0.3676 vs. 0.3497 em k=2). A hipótese de uma divisão binária "catalogada vs.
  não-catalogada" não se sustenta; a estrutura em `meta` é mais rica que isso
  (embora, como já documentado no README, ainda dominada por completude de
  metadado, não por som).
- **H2 (CONFIRMADA)**: PC1 de `meta` é dominado por `rating_scaled` (maior carga,
  0.7872) e colunas `tag_*` — 6 das 8 maiores cargas do PC1 são rating ou MyTag.
  `bpm_scaled` é a 2ª maior carga (-0.5173), mas negativa/oposta.
- **H3 (CONFIRMADA)**: treinar `meta` só nas 333 faixas com MyTag muda
  substancialmente os clusters — ARI de 0.0748 entre os rótulos do `meta`
  completo (restritos a essas 333 faixas) e os do `meta` treinado só nelas.
  Confirma que grande parte da estrutura de `meta` vem da presença/ausência de
  tag, não da faixa em si: tirar as faixas sem tag do dataset muda o que "faz
  sentido" agrupar.

## Rótulos persistidos (não sobrescreve histórico)

`track_clusters.cluster_version`: `meta_k4_2026-09`, `meta_audio_k2_2026-09`,
`audio_k2_2026-09` — adicionados. `v1_structured`/`v2_audio`/`v3_audio_only`
seguem intactos (contagens conferidas antes e depois desta etapa).

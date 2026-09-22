# Etapa 3 — Avaliação do k-NN (precision@10 por co-ocorrência em playlist)

Gerado por `src/eval_similarity.py`. Ver `docs/decisions/ADR-001-tres-espacos-e-knn.md`
pro contexto da fase e `src/similarity.py` pro sistema sendo avaliado.

## Métrica

Para cada faixa em ≥1 playlist (**832 de 1649**, 50.5% da biblioteca), a fração
dos 10 vizinhos retornados que compartilham pelo menos uma playlist com ela.
Comparado contra dois baselines (20 sorteios com seed fixa cada, média por
faixa — `n_draws_baseline`/`seed_base` no CSV):

- **aleatório**: 10 faixas sorteadas da base, sem filtro nenhum.
- **BPM+Camelot aleatório**: aplica os mesmos filtros duros do sistema real
  (BPM ±3, key compatível), mas sorteia a ordem em vez de rankear por
  similaridade — isola se o embedding agrega algo além do filtro sozinho.

## Resultados (`knn_eval.csv`)

| Espaço | Chroma | Métrica | precision@10 sistema | baseline aleatório | baseline BPM+Camelot |
|---|---|---|---|---|---|
| `meta` | n/a | cosine | **0.7041** | 0.2190 | 0.3046 |
| `meta` | n/a | euclidean | 0.6884 | 0.2190 | 0.3046 |
| `meta_audio` | com chroma | cosine | 0.4166 | 0.2185 | 0.3044 |
| `meta_audio` | com chroma | euclidean | 0.4016 | 0.2185 | 0.3044 |
| `meta_audio` | sem chroma | cosine | 0.4602 | 0.2185 | 0.3044 |
| `meta_audio` | sem chroma | euclidean | 0.4421 | 0.2185 | 0.3044 |
| `audio` | com chroma | cosine | 0.3389 | 0.2209 | 0.3044 |
| `audio` | com chroma | euclidean | 0.3427 | 0.2209 | 0.3044 |
| `audio` | sem chroma | cosine | 0.3214 | 0.2209 | 0.3044 |
| `audio` | sem chroma | euclidean | 0.3364 | 0.2209 | 0.3044 |

## Leitura dos resultados

1. **O sistema real bate os dois baselines em toda configuração** — o embedding
   + filtro duro agrega sobre filtro-sozinho-com-ordem-aleatória (0.30) em
   todos os casos, e sobre aleatório puro (~0.22) por uma margem bem maior.
   Isso confirma que a busca por vizinhança não é redundante com o filtro de
   BPM/Camelot sozinho — o ranking por similaridade importa.
2. **`meta` (0.70) vence por larga margem — e isso é o viés esperado, não uma
   vitória de qualidade.** Playlists desta biblioteca são majoritariamente
   organizadas por gênero (`Prog House` 504 faixas, `Afro House` 143, `Comercial`
   151 — ver `sql/queries` ou a tabela de playlists no README). `meta` inclui
   gênero diretamente como feature, então tem vantagem estrutural numa métrica
   que mede "co-ocorrência em playlist". Isso **não** significa que `meta`
   capture melhor semelhança sonora — a Etapa 1 já mostrou o oposto (ARI
   `meta` × `meta_audio`/`audio` ≈ 0, silhouette dominado por completude de
   metadado).
3. **`audio` (0.32–0.34) tem a menor precision@10, mas ainda bate os dois
   baselines.** Coerente com o que já se sabia: áudio não "sabe" a qual
   playlist/gênero uma faixa pertence, então uma métrica ancorada em
   organização de playlist naturalmente penaliza esse espaço — mesmo que ele
   possa estar capturando semelhança sonora real que `meta` não captura (ver
   Etapa 1, achado V2≈V3).
4. **Ablação de chroma**: em `meta_audio`, remover chroma **melhora**
   levemente a precision@10 (0.4166→0.4602 cosine, 0.4016→0.4421 euclidean).
   Em `audio` puro o efeito é pequeno e **inconsistente entre métricas**
   (cosine piora 0.3389→0.3214, euclidean melhora 0.3427→0.3364) — não dá pra
   concluir que chroma ajuda ou atrapalha de forma confiável nesta métrica com
   este volume de dados; tratar como inconclusivo, não como evidência de que
   chroma deveria ser removida.
5. **Cosine vs. euclidean**: cosine é levemente melhor que euclidean em quase
   todas as configs, exceto `audio` com chroma. Diferenças pequenas (≤0.02),
   não decisivas sozinhas.

## Faixas fora da avaliação

**817 faixas** (1649 − 832) não estão em nenhuma playlist e não entram nesta
métrica. Isso não significa que a busca não funcione pra elas — só que não há
como validar contra co-ocorrência de playlist nesses casos (não existe o
"gabarito"). `meta_audio`/`audio` avaliam 831 (não 832) porque 1 faixa
(`track_id=210208753`) não tem `audio_features` extraído.

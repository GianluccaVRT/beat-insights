# Etapa 5 — Testes reais do tool `similar_tracks` no assistente

3 pedidos reais rodados contra `src/set_assistant.py` (Ollama `llama3.1:8b`, local),
capturando o tool call exato que o modelo emitiu e a resposta final. Objetivo:
validar que a tool está exposta e funcional, e documentar falhas honestamente (não
só os casos de sucesso).

## Teste 1 — pedido direto, espaço padrão

**Prompt**: "Quero faixas parecidas com Hutchula do Sebastien Leger, pra abrir um set."

**Tool call emitido**: `similar_tracks(track_name='Hutchula', space='meta', k=10, metric='cosine', bpm_tol=3, camelot=True)` — na primeira tentativa, sem retry.

**Resultado**: ✅ sucesso. 10 vizinhos retornados no espaço `meta` (padrão), similaridades entre 93–99,9%. O modelo sintetizou corretamente em texto, citando BPM/key de cada sugestão e o percentual de similaridade — sem inventar dados que não vieram da tool.

## Teste 2 — pedido pra sair do gênero (testa se o modelo lê a dica da tool)

**Prompt**: "Ache faixas sonoramente parecidas com a Hutchula do Sebastien Leger, mas fora do gênero dela -- quero descobrir algo diferente que soe parecido."

**Tool call emitido**: `similar_tracks(track_name='Hutchula', space='audio', k=10, metric='cosine', bpm_tol=0, camelot=True)`

**Resultado**: ✅ sucesso, e mais sofisticado do que o esperado — o modelo **trocou sozinho pro espaço `audio`**, lendo a ressalva na descrição da tool ("pra achar vizinhos sonoros fora do gênero da faixa de referência, peça space='audio'"), e ainda desligou o filtro de BPM (`bpm_tol=0`, nosso sentinela) por conta própria, interpretando "algo diferente" como pedido de resultado mais amplo. 9 vizinhos retornados, similaridades 68–73% (mais baixas que o teste 1, coerente com `audio` ter silhouette/precision menores que `meta`, já documentado na Etapa 1/3).

**Ressalva encontrada, não um bug**: a resposta final afirma "são de diferentes gêneros" sobre as faixas retornadas — mas o resultado da tool `similar_tracks` **não inclui gênero nenhum** (só track_id/nome/artista/similaridade/BPM/key/deltas de áudio). O modelo não tem como verificar essa afirmação com o dado que recebeu; é uma inferência não sustentada pela tool, ainda que provavelmente verdadeira na prática (o espaço `audio` de fato não usa gênero como feature). Registrado como limitação de honestidade do modelo, não como fabricação de dados fictícios (não é o mesmo padrão de falha documentado no `set_assistant.py` pra web_search).

## Teste 3 — nome ambíguo (❌ FALHA real, documentada)

**Prompt**: "Quero faixas parecidas com Remix pra fechar o set."

**Tool call emitido**: `similar_tracks(track_name='Remix', space='meta', k=10, metric='cosine', bpm_tol=3, camelot=True)`

**Resultado da tool**: `execute_similar_tracks` corretamente **não adivinhou** qual faixa "Remix" (substring genérica, bate em 5 faixas) e devolveu um erro estruturado pedindo pra especificar melhor, com as 5 candidatas:
```json
{"error": "5 faixas encontradas contendo 'Remix' -- especifique melhor.", "candidatas": [...]}
```

**❌ Falha real do modelo**: em vez de pedir ao usuário pra escolher entre as 5 candidatas (o comportamento correto e esperado), o `llama3.1:8b` **tratou as candidatas de desambiguação como se fossem resultados de similaridade de verdade** contra uma faixa de referência inexistente chamada literalmente "Remix" — produzindo uma "análise" de compatibilidade de BPM/key fabricada e sem sentido (ex.: "tem uma chave de A... o que é muito parecido com o Remix", "chave não é compatível" — comparando contra nada real, já que a busca nunca rodou). O erro estruturado (`{"error": ..., "candidatas": [...]}`) não foi reconhecido como "pergunta de volta pro usuário"; o modelo tentou responder de qualquer forma em vez de admitir a ambiguidade.

**Causa provável**: mesma limitação de classe de modelo já documentada no `set_assistant.py` (modelos pequenos preferem sempre dar uma resposta completa a admitir que faltou informação) — aqui generalizada pra um caso novo (erro de desambiguação), não só o caso já conhecido de `web_search` não invocado. `execute_similar_tracks` está correto (não adivinha, devolve as candidatas); o gap é inteiramente na síntese do modelo em cima de um `tool_result` de erro.

**O que não foi implementado como mitigação** (ficaria pra uma iteração futura, fora do escopo desta etapa): instrução explícita no system prompt tipo "se o resultado da tool tiver a chave 'error', não invente uma resposta em cima dele -- devolva o erro/as candidatas pro usuário e pergunte qual ele quis dizer". Vale testar se isso reduz esse padrão de falha, mas não foi validado aqui.

## Resumo

| Teste | Tool call correto? | Resposta final correta? |
|---|---|---|
| 1 — pedido direto | ✅ | ✅ |
| 2 — pedido fora do gênero | ✅ (trocou espaço sozinho) | ⚠️ afirmação não sustentada pelo dado (gênero) |
| 3 — nome ambíguo | ✅ (tool devolveu erro certo) | ❌ modelo inventou análise em cima do erro |

2 de 3 tool calls corretos de primeira, sem nenhum retry necessário — melhor do que
os testes da Fase 4 original (que precisaram de `_parse_pseudo_tool_call` pra
recuperar chamadas mal-formadas). A falha do Teste 3 é de síntese sobre um erro
estruturado, não de invocação da tool -- um padrão de falha diferente do já
documentado (narrar sem invocar), registrado aqui como limite adicional conhecido
do `llama3.1:8b` nesta aplicação.

"""Assistente de set via LLM (Fase 4): chat de terminal que sugere faixas da
biblioteca a partir de um contexto de evento em texto livre (line-up, horário,
estética), descrito pelo README/spec.md.

Fluxo obrigatório, imposto via system prompt:
1. Toda sugestão de faixa passa primeiro por query_library (busca estruturada na
   base local: BPM, key Camelot compatível, gênero, MyTag, cluster de som via
   track_clusters).
2. web_search só entra se query_library não cobrir o pedido (poucas/nenhuma
   candidata, ou pedido explícito de referências novas fora da biblioteca) --
   nunca substitui a base local por padrão.

Decisão: roda 100% local/gratuito -- Ollama (llama3.1:8b) para o LLM com tool
calling, e DuckDuckGo (pacote `ddgs`, sem API key) para a busca externa. Troca a
Claude API / Tavily citados como exemplo no spec.md por uma stack sem custo,
sem exigir nenhuma chave de API -- qualquer pessoa clonando o repo consegue rodar
o assistente sem pagar por nada, na mesma linha do objetivo de reprodutibilidade
total do projeto (ver README, seção "Reprodutibilidade e privacidade").

A decisão final de mixagem em tempo real continua sendo do DJ; o assistente reduz
o espaço de busca e explica compatibilidade, não decide sozinho.

Limitação conhecida, validada contra a biblioteca real: query_library sozinho (o
caso de uso principal) é confiável -- testado com pedidos reais, retorna resultados
corretos e o modelo sintetiza bem em cima deles. Já a cadeia de 2 passos (tenta a
base local, não acha, daí chama web_search) é instável no llama3.1:8b -- às vezes o
modelo narra "vou buscar na web" em texto solto sem de fato invocar a ferramenta, e
preenche a resposta com faixas fictícias. _parse_pseudo_tool_call recupera o caso em
que ele escreve a tool call como JSON em texto (comum), mas não o caso em que ele só
descreve a ação em prosa livre. É uma limitação de classe de modelo (tool calling
encadeado em modelos pequenos), não um bug específico deste script -- documentada
aqui em vez de escondida; ver conversa de desenvolvimento para os casos de teste que
reproduzem isso.
"""

import json
import re

import ollama
from ddgs import DDGS
from sqlalchemy import text

from clustering_common import get_engine

MODEL = "llama3.1:8b"
MAX_TOOL_ITERATIONS = 6
MAX_RESULTS = 50

SYSTEM_PROMPT = """\
Você é um assistente de set para um DJ/produtor de música eletrônica. Seu papel é \
reduzir o espaço de busca na biblioteca catalogada dele e explicar compatibilidade \
técnica (key via roda de Camelot, BPM, cluster de som, MyTag) -- você NÃO decide a \
próxima faixa de um set em tempo real, isso depende de leitura de pista e é sempre \
do DJ.

Regras de busca, nessa ordem, sem exceção:
1. Para qualquer pedido de sugestão de faixa, chame query_library primeiro. Combine \
os filtros disponíveis (bpm_min/bpm_max, key_camelot, genre_contains, \
mytag_contains, min_rating, similar_to_track_id) de acordo com o que o usuário \
descreveu.
2. Só use web_search se query_library retornar poucas candidatas (ou nenhuma) para \
o pedido, ou se o usuário pedir explicitamente para descobrir referências novas \
fora da biblioteca. Nunca chame web_search antes de tentar query_library, e nunca \
substitua os resultados da biblioteca por resultados externos -- diferencie \
claramente na resposta o que veio da biblioteca do que veio da web.
3. Explique o motivo técnico das sugestões (compatibilidade de key, faixa de BPM, \
mesmo cluster de som) -- não só liste nomes de faixa.
4. Nunca invente BPM, key, rating ou cluster de som para um resultado de \
web_search -- os resultados da web só têm título, URL e um trecho de texto. Se \
essa informação técnica não vier no resultado, diga que não foi encontrada, não \
estime um valor.
"""

QUERY_LIBRARY_TOOL = {
    "type": "function",
    "function": {
        "name": "query_library",
        "description": (
            "Busca estruturada na biblioteca catalogada do DJ. Filtros combináveis: "
            "faixa de BPM, key Camelot compatível (mesma/vizinha/relativa), gênero, "
            "MyTag, rating mínimo, e faixas do mesmo cluster de som (V2, com áudio) de "
            "uma faixa de referência. Retorna até 'limit' faixas ordenadas por rating e "
            "play_count, mais a contagem total de faixas compatíveis (mesmo além do "
            "limit) -- use essa contagem pra decidir se vale complementar com web_search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "bpm_min": {"type": "number", "description": "BPM mínimo (inclusive)."},
                "bpm_max": {"type": "number", "description": "BPM máximo (inclusive)."},
                "key_camelot": {
                    "type": "string",
                    "description": "Key no formato Camelot (ex.: '8A'). Retorna faixas com key igual, vizinha (+-1) ou relativa.",
                },
                "genre_contains": {"type": "string", "description": "Substring do gênero, case-insensitive."},
                "mytag_contains": {"type": "string", "description": "Substring de um valor de MyTag, case-insensitive."},
                "min_rating": {"type": "integer", "description": "Rating mínimo (0-5)."},
                "similar_to_track_id": {
                    "type": "integer",
                    "description": "track_id de referência: restringe a faixas do mesmo cluster de som (V2 se disponível, senão V1).",
                },
                "limit": {"type": "integer", "description": f"Máximo de faixas retornadas (padrão 15, teto {MAX_RESULTS})."},
            },
        },
    },
}

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Busca externa na web (DuckDuckGo). Só usar como complemento, quando query_library não cobrir o pedido.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termos de busca."},
            },
            "required": ["query"],
        },
    },
}


_CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])[AB]$", re.IGNORECASE)


def _compatible_camelot_keys(key_camelot: str) -> list[str]:
    # Modelos menores (Ollama) às vezes mandam um valor que não é uma key Camelot
    # real (ex.: ecoam a palavra "relativa" da descrição do parâmetro). Validar
    # aqui devolve um erro claro no tool_result em vez de deixar um ValueError do
    # int() vazar como mensagem de erro genérica pro modelo.
    if not _CAMELOT_RE.match(key_camelot):
        raise ValueError(f"key_camelot inválida: {key_camelot!r} -- use o formato Camelot, ex.: '8A'.")
    num = int(key_camelot[:-1])
    letter = key_camelot[-1].upper()
    other = "B" if letter == "A" else "A"
    return [
        f"{num}{letter}",
        f"{(num % 12) + 1}{letter}",
        f"{((num + 10) % 12) + 1}{letter}",
        f"{num}{other}",
    ]


def _clean(value):
    """Normaliza placeholders que o modelo local manda no lugar de "campo omitido"
    (string "None"/"null"/vazia) para None de verdade."""
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null", "n/a"}:
        return None
    return value


def query_library(engine, **filters) -> dict:
    filters = {k: _clean(v) for k, v in filters.items()}
    where = ["1 = 1"]
    params: dict = {}

    if filters.get("bpm_min") is not None:
        where.append("t.bpm >= :bpm_min")
        params["bpm_min"] = filters["bpm_min"]
    if filters.get("bpm_max") is not None:
        where.append("t.bpm <= :bpm_max")
        params["bpm_max"] = filters["bpm_max"]
    if filters.get("genre_contains"):
        # Modelos menores (Ollama) às vezes mandam vários gêneros separados por
        # vírgula num único filtro (ex.: "organic house, afro house") -- trata
        # cada termo como uma alternativa (OR) em vez de buscar a string inteira.
        genre_terms = [g.strip() for g in filters["genre_contains"].split(",") if g.strip()]
        genre_clauses = []
        for i, term in enumerate(genre_terms):
            genre_clauses.append(f"t.genre ILIKE :genre{i}")
            params[f"genre{i}"] = f"%{term}%"
        if genre_clauses:
            where.append(f"({' OR '.join(genre_clauses)})")
    if filters.get("min_rating") is not None:
        where.append("t.rating >= :min_rating")
        params["min_rating"] = filters["min_rating"]

    key_camelot = filters.get("key_camelot")
    if key_camelot:
        keys = _compatible_camelot_keys(key_camelot)
        placeholders = ", ".join(f":key{i}" for i in range(len(keys)))
        where.append(f"t.key_camelot IN ({placeholders})")
        params.update({f"key{i}": k for i, k in enumerate(keys)})

    joins = []
    if filters.get("mytag_contains"):
        joins.append("JOIN track_mytag tm ON tm.track_id = t.track_id")
        joins.append("JOIN mytag_values mv ON mv.value_id = tm.value_id")
        where.append("mv.value_name ILIKE :mytag")
        params["mytag"] = f"%{filters['mytag_contains']}%"

    # Modelos menores (Ollama) preenchem campos opcionais com um valor-placeholder
    # (0, "") em vez de omiti-los -- 0 nunca é um track_id real (IDs do Rekordbox
    # são grandes), então trata como "não informado" e ignora o filtro.
    similar_to = filters.get("similar_to_track_id") or None
    if similar_to is not None:
        cluster_row = engine.connect().execute(
            text(
                """
                SELECT cluster_version, cluster_label FROM track_clusters
                WHERE track_id = :tid
                ORDER BY CASE cluster_version WHEN 'v2_audio' THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {"tid": similar_to},
        ).fetchone()
        if cluster_row is None:
            return {"error": f"track_id {similar_to} não tem cluster calculado.", "matches": [], "total_matches": 0}
        joins.append(
            "JOIN track_clusters tc ON tc.track_id = t.track_id "
            "AND tc.cluster_version = :cluster_version AND tc.cluster_label = :cluster_label"
        )
        params["cluster_version"] = cluster_row.cluster_version
        params["cluster_label"] = cluster_row.cluster_label
        where.append("t.track_id != :similar_to")
        params["similar_to"] = similar_to

    limit = min(int(filters.get("limit") or 15), MAX_RESULTS)

    query = f"""
        SELECT DISTINCT t.track_id, t.name, t.artist, t.key_camelot, t.bpm, t.genre,
               t.rating, t.play_count
        FROM tracks t
        {' '.join(joins)}
        WHERE {' AND '.join(where)}
        ORDER BY t.rating DESC, t.play_count DESC, t.name
        LIMIT :limit
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query), {**params, "limit": limit}).mappings().all()
        count_query = f"SELECT count(DISTINCT t.track_id) FROM tracks t {' '.join(joins)} WHERE {' AND '.join(where)}"
        total = conn.execute(text(count_query), params).scalar()

    return {"matches": [dict(r) for r in rows], "total_matches": total}


def web_search(query: str) -> dict:
    results = DDGS().text(query, max_results=5)
    return {"results": [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]}


def execute_tool(engine, name: str, tool_input: dict) -> str:
    try:
        if name == "query_library":
            result = query_library(engine, **tool_input)
        elif name == "web_search":
            result = web_search(**tool_input)
        else:
            result = {"error": f"ferramenta desconhecida: {name}"}
    except Exception as exc:  # noqa: BLE001 -- erro de ferramenta vira tool_result, não derruba o chat
        result = {"error": str(exc)}
    return json.dumps(result, default=str)


_PSEUDO_CALL_RE = re.compile(r'\{.*"name"\s*:\s*"(query_library|web_search)".*\}', re.DOTALL)


def _parse_pseudo_tool_call(content: str) -> tuple[str, dict] | None:
    """llama3.1:8b às vezes, em vez de emitir um tool_call de verdade, escreve o
    JSON da chamada como texto normal na resposta (falha conhecida de tool calling
    em modelos menores). Detecta esse padrão e trata como se fosse uma chamada real,
    em vez de deixar a resposta parecer uma tool call que nunca rodou."""
    match = _PSEUDO_CALL_RE.search(content)
    if not match:
        return None
    raw = match.group(0)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # o modelo às vezes escreve literais Python (None/True/False) em vez de
        # JSON (null/true/false) nesse pseudo tool-call -- tenta normalizar antes
        # de desistir.
        normalized = re.sub(r"\bNone\b", "null", raw)
        normalized = re.sub(r"\bTrue\b", "true", normalized)
        normalized = re.sub(r"\bFalse\b", "false", normalized)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return None
    args = payload.get("parameters") or payload.get("arguments") or {}
    return payload["name"], args


def run_turn(engine, messages: list) -> str:
    response = None
    for _ in range(MAX_TOOL_ITERATIONS):
        response = ollama.chat(model=MODEL, messages=messages, tools=[QUERY_LIBRARY_TOOL, WEB_SEARCH_TOOL])
        messages.append(response["message"])

        tool_calls = list(response["message"].tool_calls or [])
        if tool_calls:
            for call in tool_calls:
                result = execute_tool(engine, call.function.name, dict(call.function.arguments))
                messages.append({"role": "tool", "content": result})
            continue

        pseudo = _parse_pseudo_tool_call(response["message"].content or "")
        if pseudo is None:
            break
        name, args = pseudo
        result = execute_tool(engine, name, args)
        messages.append({"role": "tool", "content": result})

    return response["message"].content or ""


def main() -> None:
    engine = get_engine()
    messages: list = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Assistente de set (Ollama/{MODEL}, 100% local) -- descreva o contexto do evento (linha vazia ou 'sair' pra encerrar).\n")
    while True:
        try:
            user_input = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in {"sair", "exit", "quit"}:
            break

        messages.append({"role": "user", "content": user_input})
        reply = run_turn(engine, messages)
        print(f"\nassistente> {reply}\n")


if __name__ == "__main__":
    main()

"""Roda de Camelot (mixagem harmônica), compartilhada entre set_assistant.py
(tool query_library) e similarity.py (filtro duro do k-NN). Antes desta fase a
lógica vivia só em set_assistant.py -- consolidada aqui pra não duplicar (ADR-001).

Regras clássicas de compatibilidade: mesma key, key vizinha (+-1, mesma letra) e
key relativa (mesmo número, letra oposta -- troca entre maior/menor relativos).
"""

import re

CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])[AB]$", re.IGNORECASE)


def compatible_keys(key_camelot: str) -> list[str]:
    """Dada uma key no formato Camelot (ex.: '8A'), retorna as 4 keys compatíveis
    (ela mesma, vizinha +1, vizinha -1, relativa). Levanta ValueError com mensagem
    clara se `key_camelot` não for uma key Camelot válida -- modelos de LLM
    menores às vezes mandam um valor que não é (ex.: ecoam a descrição do
    parâmetro em vez do valor), e um ValueError cru do int() não é acionável."""
    if not CAMELOT_RE.match(key_camelot):
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

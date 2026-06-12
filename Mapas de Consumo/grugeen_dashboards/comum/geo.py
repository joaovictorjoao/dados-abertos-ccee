"""Normalização de nomes de municípios e geocodificação contra a tabela IBGE."""

import re
import unicodedata

import pandas as pd

# Variantes de apóstrofo (curly quotes, modifier letter, acento agudo, crase) -> '
# Escapes \u para imunidade a problemas de codificação:
#   U+2018 ' | U+2019 ' | U+02BC ʼ | U+00B4 ´ | U+0060 `
_APOSTROFOS = ("‘", "’", "ʼ", "´", "`")


def normalizar(texto: object) -> str:
    """Maiúsculas, sem acentos, apóstrofos unificados e espaços colapsados."""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()
    for apos in _APOSTROFOS:
        s = s.replace(apos, "'")
    return re.sub(r" {2,}", " ", s)

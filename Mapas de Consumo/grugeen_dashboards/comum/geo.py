"""Normalização de nomes de municípios e geocodificação contra a tabela IBGE."""

import re
import unicodedata

import pandas as pd

# Variantes de apóstrofo (curly quotes, modifier letter, acento agudo, crase) → '
_APOSTROFOS = ("'", "'", "ʼ", "´", "`")


def normalizar(texto: object) -> str:
    """Maiúsculas, sem acentos, apóstrofos unificados e espaços colapsados."""
    s = str(texto)
    # Replace apostrophe variants BEFORE normalization to preserve apostrophes
    for apos in _APOSTROFOS:
        s = s.replace(apos, "'")
    # Now normalize: NFKD removes accents, then filter combining marks
    nfkd = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()
    return re.sub(r" {2,}", " ", s)

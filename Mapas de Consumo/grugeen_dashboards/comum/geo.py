"""Normalização de nomes de municípios e geocodificação contra a tabela IBGE."""

import logging
import re
import unicodedata

import pandas as pd

# Variantes de apóstrofo que sobrevivem ao NFKD são unificadas em apóstrofo reto:
#   U+2018 ‘ | U+2019 ‘ | U+02BC ʼ | U+0060 `
# Obs.: U+00B4 (´) NÃO entra aqui — no NFKD ele vira espaço antes da substituição
# (decompõe em espaço + acento combinante), comportamento idêntico ao legado.
_APOSTROFOS = ('‘', '’', 'ʼ', '`')


def normalizar(texto: object) -> str:
    """Maiúsculas, sem acentos, apóstrofos unificados e espaços colapsados."""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()
    for apos in _APOSTROFOS:
        s = s.replace(apos, "'")
    return re.sub(r" {2,}", " ", s)


def geocodificar(
    df_local: pd.DataFrame,
    df_municipios: pd.DataFrame,
    coluna_local: str,
    aliases: dict[tuple[str, str], str],
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Casa `df_local[coluna_local]` + `df_local["uf"]` contra a tabela IBGE
    (`df_municipios` com colunas nome_norm, uf_norm, latitude, longitude,
    codigo_ibge). `aliases` corrige variações de grafia (chave normalizada +
    UF → nome IBGE normalizado). Retorna só as linhas com coordenada encontrada.
    """
    df = df_local.copy()
    df["local_norm"] = df[coluna_local].apply(normalizar)
    df["local_norm"] = df.apply(
        lambda r: aliases.get((r["local_norm"], r["uf"]), r["local_norm"]), axis=1
    )

    lookup = df_municipios[["nome_norm", "uf_norm", "latitude", "longitude", "codigo_ibge"]]
    df_merged = df.merge(
        lookup,
        left_on=["local_norm", "uf"],
        right_on=["nome_norm", "uf_norm"],
        how="left",
    )

    total = len(df_merged)
    encontradas = int(df_merged["latitude"].notna().sum())
    logger.info(
        "Geocodificação: %d/%d locais (%.0f%%)",
        encontradas, total, 100 * encontradas / total if total else 0,
    )
    sem = df_merged[df_merged["latitude"].isna()][coluna_local].unique()
    if len(sem):
        logger.warning(
            "Sem coords (%d): %s%s",
            len(sem), ", ".join(map(str, sem[:8])), " ..." if len(sem) > 8 else "",
        )
    return df_merged.dropna(subset=["latitude", "longitude"]).copy()

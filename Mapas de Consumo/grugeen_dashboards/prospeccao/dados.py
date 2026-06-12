"""Camada de dados da seção de Prospecção: resumo CNAE e agregação por município."""

import logging
from pathlib import Path

import pandas as pd

from grugeen_dashboards.comum.geo import normalizar
from grugeen_dashboards.comum.regioes import UF_PARA_REGIAO
from grugeen_dashboards.prospeccao.aliases import ALIASES_PROSPECCAO
from grugeen_dashboards.prospeccao.constantes import DEMANDA_kW


def carregar_resumo(arquivo_resumo: Path, logger: logging.Logger) -> pd.DataFrame:
    """Lê o CSV resumo município×CNAE e calcula a demanda estimada (kW)."""
    logger.info("Carregando %s ...", Path(arquivo_resumo).name)
    df = pd.read_csv(arquivo_resumo, sep=";", dtype=str, encoding="utf-8-sig")
    df["total_empresas"] = pd.to_numeric(df["total_empresas"], errors="coerce").fillna(0)
    df["matrizes"] = pd.to_numeric(df["matrizes"], errors="coerce").fillna(0)
    df["cnae_tier"] = pd.to_numeric(df["cnae_tier"], errors="coerce").fillna(3)
    df["demanda_kW"] = df["cnae_divisao"].map(DEMANDA_kW).fillna(300) * df["total_empresas"]
    logger.info("  %d linhas (combinações município × CNAE)", len(df))
    return df

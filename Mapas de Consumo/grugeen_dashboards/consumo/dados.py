"""Camada de dados da seção de Consumo: agregação e enriquecimento (ACL)."""

import json
import logging
from pathlib import Path

import duckdb
import pandas as pd

from grugeen_dashboards.comum import baixar_recurso, fetch, normalizar
from grugeen_dashboards.comum.regioes import IBGE_PARA_UF, UF_PARA_REGIAO
from grugeen_dashboards.consumo.aliases import ALIASES_CONSUMO


def calcular_per_capita(
    df_geo: pd.DataFrame, df_pop: pd.DataFrame, logger: logging.Logger
) -> pd.DataFrame:
    """Junta consumo geocodificado à população e calcula MWh/hab e consumidores/100k."""
    df = df_geo.copy()
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.strip().str.zfill(7)

    df_p = df_pop[["codigo_ibge", "populacao"]].copy()
    df_p["codigo_ibge"] = df_p["codigo_ibge"].astype(str).str.zfill(7)

    df_merged = df.merge(df_p, on="codigo_ibge", how="left")
    encontrados = int(df_merged["populacao"].notna().sum())
    logger.info(
        "Populacao: %d/%d municípios com dados (%.0f%%)",
        encontrados, len(df_merged),
        100 * encontrados / len(df_merged) if len(df_merged) else 0,
    )

    mask = df_merged["populacao"] > 0
    # .where(mask) mantém float64 nativo — None/object causaria problemas no Plotly
    df_merged["mwh_por_habitante"] = (
        df_merged["consumo_total_mwh"] / df_merged["populacao"]
    ).where(mask)
    df_merged["consumidores_por_100k"] = (
        df_merged["n_consumidores"] * 100_000 / df_merged["populacao"]
    ).where(mask)
    df_merged["regiao"] = df_merged["uf"].map(UF_PARA_REGIAO).fillna("")
    if "distribuidora" not in df_merged.columns:
        df_merged["distribuidora"] = ""
    return df_merged


def calcular_lacunas(
    df_municipios_ibge: pd.DataFrame,
    df_pop: pd.DataFrame,
    codigos_dataset: set[str],
    logger: logging.Logger,
) -> pd.DataFrame:
    """Retorna municípios do IBGE sem nenhum consumidor ACL, com sua população."""
    df = df_municipios_ibge[
        ~df_municipios_ibge["codigo_ibge"].isin(codigos_dataset)
    ][["codigo_ibge", "nome", "uf_norm"]].copy()

    df_p = df_pop[["codigo_ibge", "populacao"]].copy()
    df_p["codigo_ibge"] = df_p["codigo_ibge"].astype(str).str.zfill(7)
    df = df.merge(df_p, on="codigo_ibge", how="left")
    df = df[df["populacao"].notna() & (df["populacao"] > 0)].copy()
    logger.info(
        "Lacunas: %d municípios sem consumidores ACL (de %d no IBGE)",
        len(df), len(df_municipios_ibge),
    )
    return df

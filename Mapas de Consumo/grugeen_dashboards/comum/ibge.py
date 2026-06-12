"""Loaders de dados de referência do IBGE, compartilhados entre as seções."""

import json
import logging
from pathlib import Path

import pandas as pd

from grugeen_dashboards.comum.http import baixar_recurso, fetch
from grugeen_dashboards.comum.geo import normalizar
from grugeen_dashboards.comum.regioes import IBGE_PARA_UF


def carregar_municipios(
    municipios_url: str, cache_path: Path, logger: logging.Logger
) -> pd.DataFrame:
    """Baixa (ou usa cache) a tabela de municípios IBGE e adiciona colunas normalizadas."""
    baixar_recurso(municipios_url, cache_path, logger)
    df = pd.read_csv(cache_path, encoding="utf-8", dtype=str)
    df["nome_norm"] = df["nome"].apply(normalizar)
    df["uf_norm"] = df["codigo_uf"].map(IBGE_PARA_UF)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.strip().str.zfill(7)
    logger.info("Municípios IBGE: %d registros", len(df))
    return df


def baixar_populacao(
    populacao_url: str, cache_path: Path, logger: logging.Logger
) -> pd.DataFrame:
    """População por município (Censo 2022, API IBGE), com cache em CSV."""
    if Path(cache_path).exists():
        logger.info("Cache: %s", Path(cache_path).name)
        df = pd.read_csv(cache_path, dtype=str)
        df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
        return df

    logger.info("Baixando dados do Censo 2022 ...")
    raw = fetch(populacao_url, timeout=30)
    data = json.loads(raw.decode("utf-8"))
    series = data[0]["resultados"][0]["series"]
    rows = [
        {
            "codigo_ibge": s["localidade"]["id"].strip().zfill(7),
            "populacao": s["serie"].get("2022", ""),
        }
        for s in series
    ]
    df = pd.DataFrame(rows)
    df.to_csv(cache_path, index=False, encoding="utf-8")
    df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
    logger.info("Censo 2022: %d municípios", len(df))
    return df


def carregar_distribuidoras(cache_path: Path, logger: logging.Logger) -> dict[str, str]:
    """Lê o cache {codigo_ibge: distribuidora} (gerado pela seção de consumo)."""
    if not Path(cache_path).exists():
        logger.info("Cache distribuidoras não encontrado (gere pela seção de consumo)")
        return {}
    try:
        df = pd.read_csv(cache_path, dtype=str, encoding="utf-8")
        df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.zfill(7)
        mapping = dict(zip(df["codigo_ibge"], df["distribuidora"].fillna("").str.upper()))
        logger.info("Distribuidoras: %d municípios carregados", len(mapping))
        return mapping
    except Exception as exc:
        logger.warning("Erro ao carregar distribuidoras: %s", exc)
        return {}

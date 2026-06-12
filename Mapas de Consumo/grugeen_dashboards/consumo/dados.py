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


def agregar_por_estado(
    arquivo_entrada: Path, separador: str, logger: logging.Logger
) -> pd.DataFrame:
    """Soma consumo ACL por UF. O arquivo usa ponto decimal — TRY_CAST direto."""
    arquivo_fwd = str(arquivo_entrada).replace("\\", "/")
    logger.info("Agregando por estado ...")
    sql = f"""
    SELECT
        MES_REFERENCIA,
        TRIM(UPPER(ESTADO_CARGA))        AS uf,
        COUNT(DISTINCT CNPJ_CARGA)       AS n_consumidores,
        SUM(TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE)) AS consumo_total_mwh
    FROM read_csv('{arquivo_fwd}', delim='{separador}', header=true,
                  ignore_errors=true, all_varchar=true)
    WHERE ESTADO_CARGA IS NOT NULL AND TRIM(ESTADO_CARGA) != ''
    GROUP BY MES_REFERENCIA, TRIM(UPPER(ESTADO_CARGA))
    ORDER BY MES_REFERENCIA, uf
    """
    df = duckdb.sql(sql).df()
    df["consumo_total_gwh"] = df["consumo_total_mwh"] / 1_000
    logger.info("  %d estados", len(df))
    return df


def agregar_por_cidade(
    arquivo_entrada: Path, separador: str, logger: logging.Logger
) -> pd.DataFrame:
    """Soma consumo ACL por cidade+UF, incluindo a distribuidora dominante."""
    arquivo_fwd = str(arquivo_entrada).replace("\\", "/")
    logger.info("Agregando por cidade ...")
    sql = f"""
    SELECT
        MES_REFERENCIA,
        TRIM(UPPER(CIDADE_CARGA))        AS cidade,
        TRIM(UPPER(ESTADO_CARGA))        AS uf,
        COUNT(DISTINCT CNPJ_CARGA)       AS n_consumidores,
        SUM(TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE)) AS consumo_total_mwh,
        FIRST(TRIM(UPPER(SIGLA_PERFIL_AGENTE_DISTRIBUIDORA))
              ORDER BY TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE) DESC NULLS LAST)
              AS distribuidora
    FROM read_csv('{arquivo_fwd}', delim='{separador}', header=true,
                  ignore_errors=true, all_varchar=true)
    WHERE CIDADE_CARGA IS NOT NULL AND TRIM(CIDADE_CARGA) != ''
      AND ESTADO_CARGA IS NOT NULL AND TRIM(ESTADO_CARGA) != ''
    GROUP BY MES_REFERENCIA, TRIM(UPPER(CIDADE_CARGA)), TRIM(UPPER(ESTADO_CARGA))
    ORDER BY consumo_total_mwh DESC NULLS LAST
    """
    df = duckdb.sql(sql).df()
    logger.info("  %d municípios", len(df))
    return df


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


def salvar_distribuidoras_cache(
    df_geo: pd.DataFrame, cache_path: Path, logger: logging.Logger
) -> None:
    """Salva {codigo_ibge, distribuidora} para compartilhar com a seção de prospecção."""
    if "distribuidora" not in df_geo.columns:
        return
    df = (
        df_geo[["codigo_ibge", "distribuidora"]]
        .dropna(subset=["distribuidora"])
        .query("distribuidora != ''")
        .drop_duplicates("codigo_ibge")
        .copy()
    )
    df["distribuidora"] = df["distribuidora"].str.upper()
    df.to_csv(cache_path, index=False, encoding="utf-8")
    logger.info("Cache distribuidoras salvo: %d municípios → %s", len(df), Path(cache_path).name)

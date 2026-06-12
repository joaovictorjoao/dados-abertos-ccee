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


def agregar_por_municipio(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Agrega todas as divisões CNAE por município (tiers, demanda MW, CNAE dominante)."""
    logger.info("Agregando por município ...")
    agg = (
        df.groupby(["uf", "nome_municipio"])
        .agg(
            total_empresas=("total_empresas", "sum"),
            tier1=("total_empresas", lambda x: x[df.loc[x.index, "cnae_tier"] == 1].sum()),
            tier2=("total_empresas", lambda x: x[df.loc[x.index, "cnae_tier"] == 2].sum()),
            demanda_MW=("demanda_kW", lambda x: x.sum() / 1000),
            cnae_top=("cnae_descricao", lambda x: (
                df.loc[x.index].groupby("cnae_descricao")["total_empresas"].sum().idxmax()
            )),
        )
        .reset_index()
    )
    agg["nome_norm"] = agg["nome_municipio"].apply(normalizar)
    agg["nome_norm"] = agg.apply(
        lambda r: ALIASES_PROSPECCAO.get((r["nome_norm"], r["uf"]), r["nome_norm"]), axis=1
    )
    agg["regiao"] = agg["uf"].map(UF_PARA_REGIAO).fillna("")
    logger.info("  %d municípios únicos", len(agg))
    return agg

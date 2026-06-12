"""Contrato de dados da seção de Consumo: DataFrames → fragmento JSON (registros)."""

import logging
import math

import pandas as pd


def _limpar_nan(obj):
    """Converte NaN/inf (recursivamente) em None, para serialização JSON válida."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _limpar_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_limpar_nan(v) for v in obj]
    return obj


def _num(valor) -> float | None:
    """Float seguro: None se ausente/NaN/inf."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else v


def _registros(df_per_capita: pd.DataFrame) -> list[dict]:
    """Um registro por município, com todas as métricas (NaN → None)."""
    regs: list[dict] = []
    for _, row in df_per_capita.iterrows():
        ibge = str(row.get("codigo_ibge", "")).zfill(7)
        if not ibge or ibge == "0000000":
            continue
        mwh = _num(row.get("consumo_total_mwh"))
        pop = _num(row.get("populacao"))
        regs.append({
            "ibge": ibge,
            "nome": str(row.get("cidade", "")).title(),
            "uf": str(row.get("uf", "")),
            "regiao": str(row.get("regiao", "") or ""),
            "distribuidora": str(row.get("distribuidora", "") or ""),
            "gwh": round(mwh / 1000, 4) if mwh is not None else None,
            "mwh_hab": _num(row.get("mwh_por_habitante")),
            "cons_100k": _num(row.get("consumidores_por_100k")),
            "pop": int(pop) if pop and pop > 0 else 0,
            "nc": int(row.get("n_consumidores") or 0),
        })
    return regs


def _lacunas(df_lacunas: pd.DataFrame | None) -> list[dict]:
    """Municípios sem consumidores ACL, com população > 0."""
    if df_lacunas is None or df_lacunas.empty:
        return []
    out: list[dict] = []
    for _, row in df_lacunas.iterrows():
        ibge = str(row.get("codigo_ibge", "")).zfill(7)
        pop = _num(row.get("populacao"))
        if not ibge or ibge == "0000000" or not pop or pop <= 0:
            continue
        out.append({
            "ibge": ibge,
            "nome": str(row.get("nome", "")).title(),
            "uf": str(row.get("uf_norm", "")),
            "regiao": str(row.get("regiao", "") or ""),
            "pop": int(pop),
        })
    return out


def _municipios_info(
    df_per_capita: pd.DataFrame, df_lacunas: pd.DataFrame | None
) -> dict[str, dict]:
    """Mapa ibge → {nome, uf, pop} para enriquecer hover (consumo + lacunas)."""
    info: dict[str, dict] = {}
    for _, row in df_per_capita.iterrows():
        ibge = str(row.get("codigo_ibge", "")).zfill(7)
        if not ibge or ibge in info:
            continue
        pop = _num(row.get("populacao"))
        info[ibge] = {
            "nome": str(row.get("cidade", "")).title(),
            "uf": str(row.get("uf", "")),
            "pop": int(pop) if pop and pop > 0 else 0,
        }
    if df_lacunas is not None and not df_lacunas.empty:
        for _, row in df_lacunas.iterrows():
            ibge = str(row.get("codigo_ibge", "")).zfill(7)
            if not ibge or ibge in info:
                continue
            pop = _num(row.get("populacao"))
            info[ibge] = {
                "nome": str(row.get("nome", "")).title(),
                "uf": str(row.get("uf_norm", "")),
                "pop": int(pop) if pop and pop > 0 else 0,
            }
    return info


_ABAS_CONSUMO: list[dict] = [
    {"id": "estado",    "label": "Por Estado",    "nivel": "uf",        "metrica": "gwh",       "unidade": "GWh",          "escala": "linear"},
    {"id": "municipio", "label": "Por Município",  "nivel": "municipio", "metrica": "gwh",       "unidade": "GWh",          "escala": "log"},
    {"id": "mwh-hab",   "label": "Per Capita",     "nivel": "municipio", "metrica": "mwh_hab",   "unidade": "MWh/hab",      "escala": "log"},
    {"id": "cons-100k", "label": "Penetração ACL", "nivel": "municipio", "metrica": "cons_100k", "unidade": "por 100k hab", "escala": "log"},
    {"id": "lacunas",   "label": "Oportunidades",  "nivel": "municipio", "metrica": "pop",       "unidade": "hab",          "escala": "log", "tipo": "lacuna"},
]


def _opcoes_distribuidora(df_per_capita: pd.DataFrame) -> list[str]:
    """Retorna lista de distribuidoras únicas e ordenadas."""
    if "distribuidora" not in df_per_capita.columns:
        return []
    vals = df_per_capita["distribuidora"].dropna().unique().tolist()
    return sorted(v for v in vals if v)


def montar_contrato_consumo(
    df_per_capita: pd.DataFrame,
    df_lacunas: pd.DataFrame | None,
    referencia: str,
    logger: logging.Logger,
) -> dict:
    """Monta o fragmento JSON da seção de consumo (registros crus; escala fica no JS)."""
    contrato = {
        "label": "Consumo",
        "referencia": str(referencia),
        "abas": [dict(a) for a in _ABAS_CONSUMO],
        "filtros_proprios": {
            "distribuidora": {
                "label": "Distribuidora",
                "depende_de": "uf",
                "opcoes": _opcoes_distribuidora(df_per_capita),
            }
        },
        "registros": _registros(df_per_capita),
        "lacunas": _lacunas(df_lacunas),
        "municipios_info": _municipios_info(df_per_capita, df_lacunas),
    }
    logger.info(
        "Contrato consumo: %d registros, %d lacunas, %d municípios no hover",
        len(contrato["registros"]), len(contrato["lacunas"]),
        len(contrato["municipios_info"]),
    )
    return _limpar_nan(contrato)

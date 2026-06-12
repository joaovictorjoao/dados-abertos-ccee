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

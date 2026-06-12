import logging
import numpy as np
import pandas as pd
from grugeen_dashboards.consumo.dados import calcular_per_capita

_LOG = logging.getLogger("t")


def _geo():
    return pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407"],   # São Paulo, Florianópolis
        "uf": ["SP", "SC"],
        "consumo_total_mwh": [1000.0, 500.0],
        "n_consumidores": [10, 5],
    })


def _pop():
    return pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407"],
        "populacao": [1_000_000.0, 500_000.0],
    })


def test_per_capita_calcula_mwh_e_consumidores():
    out = calcular_per_capita(_geo(), _pop(), _LOG)
    sp = out[out["codigo_ibge"] == "3550308"].iloc[0]
    assert sp["mwh_por_habitante"] == 0.001            # 1000 / 1_000_000
    assert sp["consumidores_por_100k"] == 1.0          # 10 * 100_000 / 1_000_000
    assert sp["regiao"] == "Sudeste"


def test_per_capita_populacao_zero_ou_ausente_vira_nan():
    geo = _geo()
    pop = pd.DataFrame({"codigo_ibge": ["3550308", "4205407"], "populacao": [0.0, np.nan]})
    out = calcular_per_capita(geo, pop, _LOG)
    assert out["mwh_por_habitante"].isna().all()
    assert out["consumidores_por_100k"].isna().all()


def test_per_capita_cria_coluna_distribuidora_se_ausente():
    out = calcular_per_capita(_geo(), _pop(), _LOG)
    assert "distribuidora" in out.columns

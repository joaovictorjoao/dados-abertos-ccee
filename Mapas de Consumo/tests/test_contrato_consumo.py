import logging
import math
import numpy as np
import pandas as pd
from grugeen_dashboards.consumo.contrato import _limpar_nan, _registros

_LOG = logging.getLogger("t")


def test_limpar_nan_converte_nan_e_inf_em_none():
    assert _limpar_nan(float("nan")) is None
    assert _limpar_nan(float("inf")) is None
    assert _limpar_nan(1.5) == 1.5
    assert _limpar_nan({"a": float("nan"), "b": 2}) == {"a": None, "b": 2}
    assert _limpar_nan([1.0, float("nan")]) == [1.0, None]


def _df_pc():
    return pd.DataFrame({
        "codigo_ibge": ["4205407", "3550308"],
        "cidade": ["FLORIANOPOLIS", "SAO PAULO"],
        "uf": ["SC", "SP"],
        "regiao": ["Sul", "Sudeste"],
        "distribuidora": ["CELESC", "CPFL"],
        "consumo_total_mwh": [500.0, 1000.0],
        "n_consumidores": [5, 10],
        "populacao": [500000.0, 1000000.0],
        "mwh_por_habitante": [0.001, 0.001],
        "consumidores_por_100k": [1.0, 1.0],
    })


def test_registros_um_por_municipio_com_metricas():
    regs = _registros(_df_pc())
    assert len(regs) == 2
    flor = next(r for r in regs if r["ibge"] == "4205407")
    assert flor["nome"] == "Florianopolis"
    assert flor["uf"] == "SC"
    assert flor["regiao"] == "Sul"
    assert flor["distribuidora"] == "CELESC"
    assert flor["gwh"] == 0.5
    assert flor["nc"] == 5
    assert flor["pop"] == 500000


def test_registros_populacao_ausente_metricas_none():
    df = _df_pc()
    df.loc[0, "mwh_por_habitante"] = np.nan
    df.loc[0, "consumidores_por_100k"] = np.nan
    regs = _registros(df)
    flor = next(r for r in regs if r["ibge"] == "4205407")
    assert flor["mwh_hab"] is None
    assert flor["cons_100k"] is None

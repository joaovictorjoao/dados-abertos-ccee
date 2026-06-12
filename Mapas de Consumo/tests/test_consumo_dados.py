import logging
import numpy as np
import pandas as pd
from grugeen_dashboards.consumo.dados import (
    calcular_per_capita,
    calcular_lacunas,
    agregar_por_estado,
    agregar_por_cidade,
)

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


def _ibge():
    return pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407", "3304557"],  # SP, Floripa, Rio
        "nome": ["São Paulo", "Florianópolis", "Rio de Janeiro"],
        "uf_norm": ["SP", "SC", "RJ"],
    })


def test_lacunas_retorna_municipios_fora_do_dataset_com_populacao():
    pop = pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407", "3304557"],
        "populacao": [1_000_000.0, 500_000.0, 6_000_000.0],
    })
    # dataset ACL só cobre São Paulo → lacunas = Floripa e Rio
    out = calcular_lacunas(_ibge(), pop, {"3550308"}, _LOG)
    assert set(out["codigo_ibge"]) == {"4205407", "3304557"}


def test_lacunas_descarta_sem_populacao():
    pop = pd.DataFrame({
        "codigo_ibge": ["4205407", "3304557"],
        "populacao": [500_000.0, np.nan],
    })
    out = calcular_lacunas(_ibge(), pop, {"3550308"}, _LOG)
    assert set(out["codigo_ibge"]) == {"4205407"}   # Rio cai (pop NaN)


def _csv_consumo(tmp_path):
    # CSV pequeno no formato CCEE (delim ';', ponto decimal)
    p = tmp_path / "mini.csv"
    p.write_text(
        "MES_REFERENCIA;ESTADO_CARGA;CIDADE_CARGA;CNPJ_CARGA;CONSUMO_CARGA_ACL;SIGLA_PERFIL_AGENTE_DISTRIBUIDORA\n"
        "202604;SP;SAO PAULO;111;100.5;CPFL\n"
        "202604;SP;SAO PAULO;222;200.0;CPFL\n"
        "202604;SC;FLORIANOPOLIS;333;50.0;CELESC\n",
        encoding="utf-8",
    )
    return p


def test_agregar_por_estado_soma_e_converte_gwh(tmp_path):
    df = agregar_por_estado(_csv_consumo(tmp_path), ";", _LOG)
    sp = df[df["uf"] == "SP"].iloc[0]
    assert sp["n_consumidores"] == 2
    assert sp["consumo_total_mwh"] == 300.5
    assert abs(sp["consumo_total_gwh"] - 0.3005) < 1e-9


def test_agregar_por_cidade_inclui_distribuidora_dominante(tmp_path):
    df = agregar_por_cidade(_csv_consumo(tmp_path), ";", _LOG)
    sp = df[df["cidade"] == "SAO PAULO"].iloc[0]
    assert sp["uf"] == "SP"
    assert sp["n_consumidores"] == 2
    assert sp["distribuidora"] == "CPFL"

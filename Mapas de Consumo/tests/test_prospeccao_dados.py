import logging
import pandas as pd
from grugeen_dashboards.prospeccao.dados import carregar_resumo

_LOG = logging.getLogger("t")


def _csv_resumo(tmp_path):
    p = tmp_path / "resumo.csv"
    p.write_text(
        "uf;nome_municipio;cnae_divisao;cnae_descricao;cnae_tier;total_empresas;matrizes\n"
        "SP;SAO PAULO;24;Metalurgia;1;10;8\n"
        "SP;SAO PAULO;47;Varejo;3;100;90\n",
        encoding="utf-8-sig",
    )
    return p


def test_carregar_resumo_converte_numeros_e_calcula_demanda(tmp_path):
    df = carregar_resumo(_csv_resumo(tmp_path), _LOG)
    metal = df[df["cnae_divisao"] == "24"].iloc[0]
    # demanda_kW = DEMANDA_kW["24"] (3000) * total_empresas (10) = 30000
    assert metal["total_empresas"] == 10
    assert metal["demanda_kW"] == 30000
    assert metal["cnae_tier"] == 1


def test_carregar_resumo_divisao_desconhecida_usa_300(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(
        "uf;nome_municipio;cnae_divisao;cnae_descricao;cnae_tier;total_empresas;matrizes\n"
        "SP;X;99;Desconhecido;3;2;1\n",
        encoding="utf-8-sig",
    )
    df = carregar_resumo(p, _LOG)
    assert df.iloc[0]["demanda_kW"] == 600   # 300 fallback * 2

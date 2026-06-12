from grugeen_dashboards.comum.regioes import (
    UF_PARA_IBGE, IBGE_PARA_UF, UF_PARA_REGIAO,
)


def test_27_unidades_federativas():
    assert len(UF_PARA_IBGE) == 27
    assert len(UF_PARA_REGIAO) == 27


def test_uf_para_ibge_valores_conhecidos():
    assert UF_PARA_IBGE["SP"] == "35"
    assert UF_PARA_IBGE["SC"] == "42"
    assert UF_PARA_IBGE["RR"] == "14"


def test_ibge_para_uf_e_inverso():
    assert IBGE_PARA_UF["35"] == "SP"
    assert all(IBGE_PARA_UF[v] == k for k, v in UF_PARA_IBGE.items())


def test_uf_para_regiao():
    assert UF_PARA_REGIAO["SC"] == "Sul"
    assert UF_PARA_REGIAO["BA"] == "Nordeste"
    assert UF_PARA_REGIAO["SP"] == "Sudeste"
    assert UF_PARA_REGIAO["AM"] == "Norte"
    assert UF_PARA_REGIAO["GO"] == "Centro-Oeste"

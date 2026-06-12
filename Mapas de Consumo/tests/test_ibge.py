import json as _json
import logging
import pandas as pd
import grugeen_dashboards.comum.ibge as ibge
from grugeen_dashboards.comum.ibge import (
    carregar_municipios, baixar_populacao, carregar_distribuidoras,
)

_LOG = logging.getLogger("t")


def test_carregar_municipios_usa_cache_e_normaliza(tmp_path):
    cache = tmp_path / "municipios.csv"
    cache.write_text(
        "codigo_ibge,nome,codigo_uf,latitude,longitude\n"
        "3550308,São Paulo,35,-23.5,-46.6\n",
        encoding="utf-8",
    )
    df = carregar_municipios("http://ignorado", cache, _LOG)
    row = df.iloc[0]
    assert row["nome_norm"] == "SAO PAULO"
    assert row["uf_norm"] == "SP"
    assert row["codigo_ibge"] == "3550308"
    assert row["latitude"] == -23.5


def test_baixar_populacao_parseia_json(tmp_path, monkeypatch):
    cache = tmp_path / "pop.csv"
    fake = [{"resultados": [{"series": [
        {"localidade": {"id": "3550308"}, "serie": {"2022": "1000000"}},
    ]}]}]
    monkeypatch.setattr(ibge, "fetch", lambda url, timeout=30: _json.dumps(fake).encode("utf-8"))
    df = baixar_populacao("http://api", cache, _LOG)
    assert df.iloc[0]["codigo_ibge"] == "3550308"
    assert df.iloc[0]["populacao"] == 1_000_000
    assert cache.exists()


def test_carregar_distribuidoras_le_cache_para_dict(tmp_path):
    cache = tmp_path / "dist.csv"
    cache.write_text(
        "codigo_ibge,distribuidora\n3550308,cpfl\n4205407,celesc\n",
        encoding="utf-8",
    )
    mapping = carregar_distribuidoras(cache, _LOG)
    assert mapping["3550308"] == "CPFL"
    assert mapping["4205407"] == "CELESC"


def test_carregar_distribuidoras_ausente_retorna_vazio(tmp_path):
    assert carregar_distribuidoras(tmp_path / "nao_existe.csv", _LOG) == {}

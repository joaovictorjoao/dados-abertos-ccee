import logging
import pandas as pd
from grugeen_dashboards.comum.geo import normalizar, geocodificar


def test_normalizar_remove_acentos_e_caixa_alta():
    assert normalizar("São Paulo") == "SAO PAULO"


def test_normalizar_colapsa_espacos_duplos():
    assert normalizar("RIO   DE  JANEIRO") == "RIO DE JANEIRO"


def test_normalizar_unifica_apostrofos():
    # Aspas curvas (U+2019) sobrevivem ao NFKD e sao unificadas em apostrofo reto.
    assert normalizar("Dias d'Avila") == "DIAS D'AVILA"


def test_normalizar_acento_agudo_isolado_vira_espaco():
    # U+00B4 (´) decompoe em espaco+combinante no NFKD → vira espaco (igual ao legado).
    assert normalizar("Olhos d´Agua") == "OLHOS D AGUA"


def test_normalizar_aceita_nao_string():
    assert normalizar(123) == "123"


def _municipios_fake():
    return pd.DataFrame({
        "nome_norm": ["SAO PAULO", "DIAS D'AVILA"],
        "uf_norm":   ["SP", "BA"],
        "latitude":  [-23.5, -12.6],
        "longitude": [-46.6, -38.3],
        "codigo_ibge": ["3550308", "2910057"],
    })


def test_geocodificar_casa_por_nome_e_uf():
    df = pd.DataFrame({"cidade": ["São Paulo"], "uf": ["SP"]})
    out = geocodificar(df, _municipios_fake(), "cidade", {}, logging.getLogger("t"))
    assert len(out) == 1
    assert out.iloc[0]["codigo_ibge"] == "3550308"


def test_geocodificar_aplica_alias():
    df = pd.DataFrame({"cidade": ["DIAS D AVILA"], "uf": ["BA"]})
    aliases = {("DIAS D AVILA", "BA"): "DIAS D'AVILA"}
    out = geocodificar(df, _municipios_fake(), "cidade", aliases, logging.getLogger("t"))
    assert len(out) == 1
    assert out.iloc[0]["codigo_ibge"] == "2910057"


def test_geocodificar_descarta_sem_coordenada():
    df = pd.DataFrame({"cidade": ["Cidade Inexistente"], "uf": ["SP"]})
    out = geocodificar(df, _municipios_fake(), "cidade", {}, logging.getLogger("t"))
    assert len(out) == 0

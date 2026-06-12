from grugeen_dashboards.comum.geo import normalizar


def test_normalizar_remove_acentos_e_caixa_alta():
    assert normalizar("São Paulo") == "SAO PAULO"


def test_normalizar_colapsa_espacos_duplos():
    assert normalizar("RIO   DE  JANEIRO") == "RIO DE JANEIRO"


def test_normalizar_unifica_apostrofos():
    # Aspas curvas (U+2019) sobrevivem ao NFKD e são unificadas em apóstrofo reto.
    assert normalizar("Dias d'Avila") == "DIAS D'AVILA"


def test_normalizar_acento_agudo_isolado_vira_espaco():
    # U+00B4 (´) decompõe em espaço+combinante no NFKD → vira espaço (igual ao legado).
    assert normalizar("Olhos d´Agua") == "OLHOS D AGUA"


def test_normalizar_aceita_nao_string():
    assert normalizar(123) == "123"

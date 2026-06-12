from grugeen_dashboards.comum.formato import (
    formatar_br, fmt_gwh, fmt_mwh, fmt_mwh_hab, fmt_cons_100k, fmt_pop,
)


def test_formatar_br_milhar_e_decimal():
    assert formatar_br(1234567.89, 2) == "1.234.567,89"


def test_formatar_br_zero_decimais():
    assert formatar_br(1234, 0) == "1.234"


def test_formatar_br_negativo():
    assert formatar_br(-1234.5, 1) == "-1.234,5"


def test_fmt_gwh():
    assert fmt_gwh(12.5) == "12,50 GWh"


def test_fmt_mwh():
    assert fmt_mwh(12.5) == "12,5 MWh"


def test_fmt_mwh_hab():
    assert fmt_mwh_hab(0.123) == "0,123 MWh/hab"


def test_fmt_cons_100k():
    assert fmt_cons_100k(3.0) == "3,0 por 100k hab"


def test_fmt_pop():
    assert fmt_pop(15000.0) == "15.000 hab"

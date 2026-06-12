"""Formatação numérica no padrão brasileiro (ponto de milhar, vírgula decimal)."""


def formatar_br(valor: float, decimais: int = 2) -> str:
    """Formata número no padrão brasileiro (ponto milhar, vírgula decimal)."""
    fmt = f"{valor:,.{decimais}f}"
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_gwh(v: float) -> str:
    return formatar_br(v, 2) + " GWh"


def fmt_mwh(v: float) -> str:
    return formatar_br(v, 1) + " MWh"


def fmt_mwh_hab(v: float) -> str:
    return formatar_br(v, 3) + " MWh/hab"


def fmt_cons_100k(v: float) -> str:
    return formatar_br(v, 1) + " por 100k hab"


def fmt_pop(v: float) -> str:
    return formatar_br(int(v), 0) + " hab"

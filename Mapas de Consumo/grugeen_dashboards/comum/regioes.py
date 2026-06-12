"""Dados de referência das Unidades Federativas (UF ↔ IBGE ↔ região)."""

# UF (sigla) → código numérico IBGE
UF_PARA_IBGE: dict[str, str] = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}

# Código numérico IBGE → UF (sigla)
IBGE_PARA_UF: dict[str, str] = {v: k for k, v in UF_PARA_IBGE.items()}

_UF_REGIAO: dict[str, list[str]] = {
    "Norte":        ["AC", "AM", "AP", "PA", "RO", "RR", "TO"],
    "Nordeste":     ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MS", "MT"],
    "Sudeste":      ["ES", "MG", "RJ", "SP"],
    "Sul":          ["PR", "RS", "SC"],
}

# UF (sigla) → nome da região
UF_PARA_REGIAO: dict[str, str] = {
    uf: reg for reg, ufs in _UF_REGIAO.items() for uf in ufs
}

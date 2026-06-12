"""Correções de grafia RF → IBGE (prospecção).

Chave: (nome_normalizado_RF, UF) → nome_normalizado_IBGE.
Dados específicos do dataset de prospecção; não compartilhar com consumo.
"""

ALIASES_PROSPECCAO: dict[tuple[str, str], str] = {
    # CE
    ("SAO LUIZ DO CURU", "CE"): "SAO LUIS DO CURU",
    # MA
    ("PINDARE MIRIM", "MA"): "PINDARE-MIRIM",
    # MG
    ("AMPARO DA SERRA", "MG"): "AMPARO DO SERRA",
    ("BARAO DO MONTE ALTO", "MG"): "BARAO DE MONTE ALTO",
    ("BRASOPOLIS", "MG"): "BRAZOPOLIS",
    ("DONA EUZEBIA", "MG"): "DONA EUSEBIA",
    ("OLHOS-D'AGUA", "MG"): "OLHOS D'AGUA",
    ("PASSA VINTE", "MG"): "PASSA-VINTE",
    ("PINGO D'AGUA", "MG"): "PINGO-D'AGUA",
    ("SAO TOME DAS LETRAS", "MG"): "SAO THOME DAS LETRAS",
    # PA
    ("ELDORADO DOS CARAJAS", "PA"): "ELDORADO DO CARAJAS",
    ("SANTA ISABEL DO PARA", "PA"): "SANTA IZABEL DO PARA",
    # PE
    ("ITAMARACA", "PE"): "ILHA DE ITAMARACA",
    ("LAGOA DO ITAENGA", "PE"): "LAGOA DE ITAENGA",
    ("SAO CAITANO", "PE"): "SAO CAETANO",
    # RJ
    ("PARATI", "RJ"): "PARATY",
    ("TRAJANO DE MORAIS", "RJ"): "TRAJANO DE MORAES",
    # RN
    ("ASSU", "RN"): "ACU",
    ("BOA SAUDE", "RN"): "JANUARIO CICCO (BOA SAUDE)",
    ("CAMPO GRANDE", "RN"): "AUGUSTO SEVERO (CAMPO GRANDE)",
    ("OLHO D'AGUA DO BORGES", "RN"): "OLHO-D'AGUA DO BORGES",
    # RS
    ("ENTRE IJUIS", "RS"): "ENTRE-IJUIS",
    ("SANTANA DO LIVRAMENTO", "RS"): "SANT'ANA DO LIVRAMENTO",
    # SC
    ("BALNEARIO DE PICARRAS", "SC"): "BALNEARIO PICARRAS",
    # SE
    ("GRACCHO CARDOSO", "SE"): "GRACHO CARDOSO",
    # SP
    ("EMBU", "SP"): "EMBU DAS ARTES",
    ("FLORINEA", "SP"): "FLORINIA",
    ("MOJI-MIRIM", "SP"): "MOGI MIRIM",
    # TO
    ("COUTO DE MAGALHAES", "TO"): "COUTO MAGALHAES",
    ("SAO VALERIO DA NATIVIDADE", "TO"): "SAO VALERIO",
}

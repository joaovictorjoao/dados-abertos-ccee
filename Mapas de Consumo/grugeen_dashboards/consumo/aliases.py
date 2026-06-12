"""Correções de grafia de municípios do CCEE → nome normalizado IBGE (consumo).

Chave: (nome_normalizado_CCEE, UF) → nome_normalizado_IBGE.
Dados específicos do dataset de consumo; não compartilhar com prospecção.
"""

ALIASES_CONSUMO: dict[tuple[str, str], str] = {
    # BA
    ("DIAS D AVILA", "BA"): "DIAS D'AVILA",
    # CE
    ("SAO LUIZ DO CURU", "CE"): "SAO LUIS DO CURU",
    # ES
    ("CACHOEIRO DO ITAPEMIRIM", "ES"): "CACHOEIRO DE ITAPEMIRIM",
    # GO
    ("AGUA LINDAS DE GOIAS", "GO"): "AGUAS LINDAS DE GOIAS",
    # MG
    ("DONA EUZEBIA", "MG"): "DONA EUSEBIA",
    ("OLHOS D AGUA", "MG"): "OLHOS D'AGUA",
    ("SANTA RITA DO IBITIPOCA", "MG"): "SANTA RITA DE IBITIPOCA",
    # MS — CCEE tem grafia com troca de letras
    ("DEADAPOLIS", "MS"): "DEODAPOLIS",
    # MT
    ("MIRASSOL D OESTE", "MT"): "MIRASSOL D'OESTE",
    ("ROSARIO DO OESTE", "MT"): "ROSARIO OESTE",
    # PA
    ("ELDORADO DOS CARAJAS", "PA"): "ELDORADO DO CARAJAS",
    ("SALINOPLIS", "PA"): "SALINOPOLIS",   # grafia truncada no CCEE
    ("SANTA ISABEL DO PARA", "PA"): "SANTA IZABEL DO PARA",
    # PE
    ("ITAMARACA", "PE"): "ILHA DE ITAMARACA",
    ("LAGOA DO ITAENGA", "PE"): "LAGOA DE ITAENGA",
    ("SAO CAITANO", "PE"): "SAO CAETANO",
    # PR
    ("DIAMANTE D OESTE", "PR"): "DIAMANTE D'OESTE",
    ("ITAPEJARA D OESTE", "PR"): "ITAPEJARA D'OESTE",
    ("ITAPEJARA D' OESTE", "PR"): "ITAPEJARA D'OESTE",
    ("PEROLA D OESTE", "PR"): "PEROLA D'OESTE",
    ("RANCHO ALEGRE D OESTE", "PR"): "RANCHO ALEGRE D'OESTE",
    ("SAO JORGE D OESTE", "PR"): "SAO JORGE D'OESTE",
    # RJ
    ("ARMACAO DE BUZIOS", "RJ"): "ARMACAO DOS BUZIOS",
    ("PARATI", "RJ"): "PARATY",
    ("TRAJANO DE MORAIS", "RJ"): "TRAJANO DE MORAES",
    # RN
    ("ALTO DOS RODRIGUES", "RN"): "ALTO DO RODRIGUES",
    ("JANUARIO CICCO", "RN"): "JANUARIO CICCO (BOA SAUDE)",
    ("PRESIDENTE JUSCELINO", "RN"): "SERRA CAIADA",  # renomeado em 2002
    # RO
    ("ESPIGAO D OESTE", "RO"): "ESPIGAO D'OESTE",
    ("NOVA BRASILANDIA D OESTE", "RO"): "NOVA BRASILANDIA D'OESTE",
    # RS
    ("ENTRE IJUIS", "RS"): "ENTRE-IJUIS",
    ("SANTANA DO LIVRAMENTO", "RS"): "SANT'ANA DO LIVRAMENTO",
    # SC
    ("HERVAL D OESTE", "SC"): "HERVAL D'OESTE",
    ("SAO MIGUEL D OESTE", "SC"): "SAO MIGUEL DO OESTE",
    # SE
    ("ITAPORANGA D AJUDA", "SE"): "ITAPORANGA D'AJUDA",
    # SP
    ("APARECIDA D OESTE", "SP"): "APARECIDA D'OESTE",
    ("EMBU", "SP"): "EMBU DAS ARTES",
    ("ESTRELA D OESTE", "SP"): "ESTRELA D'OESTE",
    ("PALMEIRA D OESTE", "SP"): "PALMEIRA D'OESTE",
    ("SANTA BARBARA D' OESTE", "SP"): "SANTA BARBARA D'OESTE",
}

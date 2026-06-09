#!/usr/bin/env python3
# =============================================================================
# SCRIPT: Mapa interativo de consumo mensal de energia por localização
# Fonte: CCEE - Dados Abertos - consumo_horario_perfil_agente
# =============================================================================
# OBJETIVO:
#   Gerar dashboard HTML interativo com quatro visualizações do consumo ACL:
#     1) Coroplético por estado (GWh)
#     2) Coroplético por município (GWh)
#     3) Consumo per capita por município (MWh/habitante)
#     4) Penetração ACL por município (consumidores/100k habitantes)
#
# SAÍDAS (pasta "mapas/" ao lado do arquivo .gz):
#   mapa_consumo_YYYYMM.html — dashboard com 4 abas
#
# DEPENDÊNCIAS:
#   pip install duckdb pandas plotly
#
# RECURSOS EXTERNOS (baixados uma vez e cacheados):
#   - GeoJSON estados: github/codeforamerica/click_that_hood
#   - GeoJSON municípios: IBGE v2 API (1 request por estado)
#   - População: IBGE Censo 2022 API v3 (único request)
#   - Municípios lat/lon: github/kelvins/municipios-brasileiros
#
# COMO USAR:
#   python mapa_consumo_mensal.py
#   (ajustar ARQUIVO_ENTRADA abaixo se necessário)
# =============================================================================

import base64
import ctypes
import ctypes.wintypes
import gc
import gzip
import io
import json
import logging
import sys
import time
import re
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────

# Ajuste o nome do arquivo conforme o mês desejado (AAAAMM)
ARQUIVO_ENTRADA = Path(__file__).parent.parent / "Extração Consumo Horário" / "consumo_horario_perfil_agente_202604.csv.gz"

# PASTA_SAIDA fica ao lado do script (Mapas de Consumo/mapas),
# compartilhando o cache de GeoJSON com mapa_prospecao_cnpjs.py
_AQUI = Path(__file__).parent
PASTA_SAIDA = _AQUI / "mapas"
SEPARADOR = ";"
_DIST_CACHE = PASTA_SAIDA / "distribuidoras_municipios.csv"

# ─── RECURSOS EXTERNOS (baixados uma vez, cacheados em PASTA_SAIDA) ───────────

_GEOJSON_EST_CACHE = PASTA_SAIDA / "br_estados.geojson"
_GEOJSON_EST_URL = (
    "https://raw.githubusercontent.com/codeforamerica/click_that_hood"
    "/master/public/data/brazil-states.geojson"
)

_GEOJSON_MUN_CACHE = PASTA_SAIDA / "br_municipios_filtrado.geojson"
_GEOJSON_LAC_CACHE = PASTA_SAIDA / "br_municipios_lacunas.geojson"
# URL base IBGE v2 — resolucao=5 é obrigatório: é o único nível que retorna municípios
_GEOJSON_MUN_URL_BASE = (
    "https://servicodados.ibge.gov.br/api/v2/malhas"
    "/{uf_code}?resolucao=5&formato=application/vnd.geo%2Bjson"
)

_MUNICIPIOS_CACHE = PASTA_SAIDA / "municipios_ibge.csv"
_MUNICIPIOS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros"
    "/main/csv/municipios.csv"
)

_POPULACAO_CACHE = PASTA_SAIDA / "populacao_municipios.csv"
# Censo Demográfico 2022 — população total por município (tabela 4714, variável 93)
_POPULACAO_URL = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/4714"
    "/periodos/2022/variaveis/93?localidades=N6[all]"
)

# Mapeamento UF (sigla) → código numérico IBGE
_UF_PARA_IBGE: dict[str, str] = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}

# ─── IDENTIDADE VISUAL GRUGEEN ────────────────────────────────────────────────

# Logo opcional — coloque o arquivo em assets/logo.png ao lado do script
_LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

# Gradiente institucional: Off-white → Verde Claro → Verde Vivo → Verde Principal → Verde Escuro
_COLORSCALE_GRUGEEN: list[list] = [
    [0.00, "#E2E2E2"],
    [0.25, "#96D6B0"],
    [0.50, "#44AA6D"],
    [0.75, "#1D683C"],
    [1.00, "#013D1A"],
]

# Gradiente para lacunas: cinza claro → laranja claro → laranja institucional
_COLORSCALE_LACUNAS: list[list] = [
    [0.00, "#E2E2E2"],
    [0.50, "#FFAD80"],
    [1.00, "#EC6C41"],
]

_UF_REGIAO: dict[str, list[str]] = {
    "Norte":        ["AC", "AM", "AP", "PA", "RO", "RR", "TO"],
    "Nordeste":     ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MS", "MT"],
    "Sudeste":      ["ES", "MG", "RJ", "SP"],
    "Sul":          ["PR", "RS", "SC"],
}
_UF_PARA_REGIAO: dict[str, str] = {
    uf: reg for reg, ufs in _UF_REGIAO.items() for uf in ufs
}


def _logo_data_uri() -> str:
    """Retorna o logo como data URI base64; string vazia se o arquivo não existir."""
    try:
        data = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        return ""


# ─── LOGGING ──────────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    pasta_logs = _AQUI / "logs"
    pasta_logs.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = pasta_logs / f"mapa_consumo_{ts}.log"
    fmt = "%(asctime)s | %(levelname)s | %(message)s"
    stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(stream),
        ],
    )
    return logging.getLogger(__name__)


# ─── DOWNLOAD ─────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 30) -> bytes:
    """Baixa URL e retorna bytes crus (descomprime gzip se necessário)."""
    req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def _baixar_recurso(url: str, destino: Path, logger: logging.Logger) -> None:
    if destino.exists():
        logger.info("Cache: %s", destino.name)
        return
    logger.info("Baixando %s ...", destino.name)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        destino.write_bytes(_fetch(url))
        logger.info("  %.1f KB", destino.stat().st_size / 1024)
    except Exception as exc:
        logger.error("Falha: %s — %s", destino.name, exc)
        raise


# ─── AGREGA COM DUCKDB ────────────────────────────────────────────────────────

def _agregar_por_estado(logger: logging.Logger) -> pd.DataFrame:
    """Soma consumo ACL por UF e mês. O .gz usa ponto decimal — TRY_CAST direto."""
    arquivo_fwd = str(ARQUIVO_ENTRADA).replace("\\", "/")
    logger.info("Agregando por estado ...")
    t0 = time.perf_counter()
    sql = f"""
    SELECT
        MES_REFERENCIA,
        TRIM(UPPER(ESTADO_CARGA))        AS uf,
        COUNT(DISTINCT CNPJ_CARGA)       AS n_consumidores,
        SUM(TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE)) AS consumo_total_mwh
    FROM read_csv('{arquivo_fwd}', delim='{SEPARADOR}', header=true,
                  ignore_errors=true, all_varchar=true)
    WHERE ESTADO_CARGA IS NOT NULL AND TRIM(ESTADO_CARGA) != ''
    GROUP BY MES_REFERENCIA, TRIM(UPPER(ESTADO_CARGA))
    ORDER BY MES_REFERENCIA, uf
    """
    df = duckdb.sql(sql).df()
    df["consumo_total_gwh"] = df["consumo_total_mwh"] / 1_000
    logger.info("  %d estados em %.1f s", len(df), time.perf_counter() - t0)
    return df


def _agregar_por_cidade(logger: logging.Logger) -> pd.DataFrame:
    """Soma consumo ACL por cidade+UF e mês, incluindo distribuidora dominante."""
    arquivo_fwd = str(ARQUIVO_ENTRADA).replace("\\", "/")
    logger.info("Agregando por cidade ...")
    t0 = time.perf_counter()
    sql = f"""
    SELECT
        MES_REFERENCIA,
        TRIM(UPPER(CIDADE_CARGA))        AS cidade,
        TRIM(UPPER(ESTADO_CARGA))        AS uf,
        COUNT(DISTINCT CNPJ_CARGA)       AS n_consumidores,
        SUM(TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE)) AS consumo_total_mwh,
        /* distribuidora com maior consumo no município */
        FIRST(TRIM(UPPER(SIGLA_PERFIL_AGENTE_DISTRIBUIDORA))
              ORDER BY TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE) DESC NULLS LAST)
              AS distribuidora
    FROM read_csv('{arquivo_fwd}', delim='{SEPARADOR}', header=true,
                  ignore_errors=true, all_varchar=true)
    WHERE CIDADE_CARGA IS NOT NULL AND TRIM(CIDADE_CARGA) != ''
      AND ESTADO_CARGA IS NOT NULL AND TRIM(ESTADO_CARGA) != ''
    GROUP BY MES_REFERENCIA, TRIM(UPPER(CIDADE_CARGA)), TRIM(UPPER(ESTADO_CARGA))
    ORDER BY consumo_total_mwh DESC NULLS LAST
    """
    df = duckdb.sql(sql).df()
    logger.info("  %d municípios em %.1f s", len(df), time.perf_counter() - t0)
    return df


# ─── GEOCODIFICAÇÃO ───────────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()
    return re.sub(r" {2,}", " ", s)


# Mapeamento de variações nos nomes do CCEE → nome normalizado no IBGE
_ALIASES: dict[tuple[str, str], str] = {
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


def _carregar_municipios(logger: logging.Logger) -> pd.DataFrame:
    _baixar_recurso(_MUNICIPIOS_URL, _MUNICIPIOS_CACHE, logger)
    df = pd.read_csv(_MUNICIPIOS_CACHE, encoding="utf-8", dtype=str)
    df["nome_norm"] = df["nome"].apply(_normalizar)
    _ibge_para_uf = {v: k for k, v in _UF_PARA_IBGE.items()}
    df["uf_norm"] = df["codigo_uf"].map(_ibge_para_uf)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    # codigo_ibge: 7 dígitos com zero à esquerda
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.strip().str.zfill(7)
    logger.info("Municípios IBGE: %d registros", len(df))
    return df


def _geocodificar(df_cidades: pd.DataFrame, df_municipios: pd.DataFrame,
                  logger: logging.Logger) -> pd.DataFrame:
    df = df_cidades.copy()
    df["cidade_norm"] = df["cidade"].apply(_normalizar)

    # Corrige variações de grafia do CCEE que não batem com o IBGE
    df["cidade_norm"] = df.apply(
        lambda r: _ALIASES.get((r["cidade_norm"], r["uf"]), r["cidade_norm"]), axis=1
    )

    lookup = df_municipios[["nome_norm", "uf_norm", "latitude", "longitude", "codigo_ibge"]]
    df_merged = df.merge(
        lookup,
        left_on=["cidade_norm", "uf"],
        right_on=["nome_norm", "uf_norm"],
        how="left",
    )

    total = len(df_merged)
    encontradas = df_merged["latitude"].notna().sum()
    logger.info(
        "Geocodificação: %d/%d cidades (%.0f%%)",
        encontradas, total, 100 * encontradas / total if total else 0,
    )
    sem = df_merged[df_merged["latitude"].isna()]["cidade"].unique()
    if len(sem):
        logger.warning(
            "Sem coords (%d): %s%s",
            len(sem), ", ".join(sem[:8]), " ..." if len(sem) > 8 else "",
        )
    return df_merged.dropna(subset=["latitude", "longitude"]).copy()


# ─── GEOJSON DE MUNICÍPIOS (IBGE v2) ─────────────────────────────────────────

_GEOJSON_FINGERPRINT = PASTA_SAIDA / "br_municipios_fingerprint.txt"


def _geojson_valido(codigos_dataset: set[str], codigos_ausentes: set[str]) -> bool:
    """Verifica se o cache GeoJSON foi gerado para o mesmo conjunto de municípios."""
    if not (_GEOJSON_MUN_CACHE.exists() and _GEOJSON_LAC_CACHE.exists() and _GEOJSON_FINGERPRINT.exists()):
        return False
    expected = ",".join(sorted(codigos_dataset)) + "|" + ",".join(sorted(codigos_ausentes))
    return _GEOJSON_FINGERPRINT.read_text(encoding="utf-8").strip() == expected


def _baixar_geojson_municipios(
    codigos_dataset: set[str],
    codigos_ausentes: set[str],
    logger: logging.Logger,
) -> tuple[Path, Path]:
    """
    Baixa limites municipais do IBGE v2 (um request por estado) e salva dois
    caches em disco: municípios do dataset (ACL) e municípios ausentes (lacunas).
    O cache é invalidado automaticamente quando o conjunto de municípios muda.
    Retorna (Path_acl, Path_lacunas) — os dicts NÃO são mantidos em memória.
    """
    if _geojson_valido(codigos_dataset, codigos_ausentes):
        logger.info("Cache: %s", _GEOJSON_MUN_CACHE.name)
        logger.info("Cache: %s", _GEOJSON_LAC_CACHE.name)
        return _GEOJSON_MUN_CACHE, _GEOJSON_LAC_CACHE
    if _GEOJSON_MUN_CACHE.exists():
        logger.info("GeoJSON stale (conjunto de municípios mudou) — reconstruindo ...")

    logger.info("Baixando GeoJSON de municípios (27 estados, resolucao=5) ...")
    features_acl: list = []
    features_lac: list = []
    for uf_nome, uf_code in sorted(_UF_PARA_IBGE.items()):
        url = _GEOJSON_MUN_URL_BASE.format(uf_code=uf_code)
        try:
            raw = _fetch(url, timeout=30)
            gj_uf = json.loads(raw.decode("utf-8"))
            n_acl_antes = len(features_acl)
            for feat in gj_uf.get("features", []):
                codarea = str(feat.get("properties", {}).get("codarea", "")).strip().zfill(7)
                feat["properties"]["codarea"] = codarea
                if codarea in codigos_dataset:
                    features_acl.append(feat)
                elif codarea in codigos_ausentes:
                    features_lac.append(feat)
            adicionados = len(features_acl) - n_acl_antes
            total_uf = len(gj_uf.get("features", []))
            logger.info("  %s: %d/%d municípios", uf_nome, adicionados, total_uf)
            del gj_uf, raw
        except Exception as exc:
            logger.warning("  %s: erro — %s", uf_nome, exc)

    for path, features in [(_GEOJSON_MUN_CACHE, features_acl), (_GEOJSON_LAC_CACHE, features_lac)]:
        geojson = {"type": "FeatureCollection", "features": features}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, separators=(",", ":"))
        logger.info("GeoJSON salvo: %s (%.0f KB)", path.name, path.stat().st_size / 1024)

    fingerprint = ",".join(sorted(codigos_dataset)) + "|" + ",".join(sorted(codigos_ausentes))
    _GEOJSON_FINGERPRINT.write_text(fingerprint, encoding="utf-8")

    del features_acl, features_lac
    gc.collect()
    return _GEOJSON_MUN_CACHE, _GEOJSON_LAC_CACHE


# ─── DADOS POPULACIONAIS (IBGE CENSO 2022) ───────────────────────────────────

def _baixar_populacao(logger: logging.Logger) -> pd.DataFrame:
    if _POPULACAO_CACHE.exists():
        logger.info("Cache: %s", _POPULACAO_CACHE.name)
        df = pd.read_csv(_POPULACAO_CACHE, dtype=str)
        df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
        return df

    logger.info("Baixando dados do Censo 2022 ...")
    raw = _fetch(_POPULACAO_URL, timeout=30)
    data = json.loads(raw.decode("utf-8"))
    series = data[0]["resultados"][0]["series"]
    rows = [
        {
            "codigo_ibge": s["localidade"]["id"].strip().zfill(7),
            "populacao": s["serie"].get("2022", ""),
        }
        for s in series
    ]
    df = pd.DataFrame(rows)
    df.to_csv(_POPULACAO_CACHE, index=False, encoding="utf-8")
    df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
    logger.info("Censo 2022: %d municípios", len(df))
    return df


def _calcular_per_capita(df_geo: pd.DataFrame, df_pop: pd.DataFrame,
                         logger: logging.Logger) -> pd.DataFrame:
    df = df_geo.copy()
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.strip().str.zfill(7)

    df_p = df_pop[["codigo_ibge", "populacao"]].copy()
    df_p["codigo_ibge"] = df_p["codigo_ibge"].astype(str).str.zfill(7)

    df_merged = df.merge(df_p, on="codigo_ibge", how="left")
    encontrados = df_merged["populacao"].notna().sum()
    logger.info(
        "Populacao: %d/%d municípios com dados (%.0f%%)",
        encontrados, len(df_merged), 100 * encontrados / len(df_merged) if len(df_merged) else 0,
    )

    mask = df_merged["populacao"] > 0
    # .where(mask) mantém float64 nativo — None/object causaria problemas no Plotly
    df_merged["mwh_por_habitante"] = (
        df_merged["consumo_total_mwh"] / df_merged["populacao"]
    ).where(mask)
    df_merged["consumidores_por_100k"] = (
        df_merged["n_consumidores"] * 100_000 / df_merged["populacao"]
    ).where(mask)
    df_merged["regiao"] = df_merged["uf"].map(_UF_PARA_REGIAO).fillna("")
    if "distribuidora" not in df_merged.columns:
        df_merged["distribuidora"] = ""
    return df_merged


def _salvar_distribuidoras_cache(df_geo: pd.DataFrame, logger: logging.Logger) -> None:
    """Salva {codigo_ibge, distribuidora} para uso compartilhado com mapa_prospecao_cnpjs.py."""
    if "distribuidora" not in df_geo.columns:
        return
    df = (
        df_geo[["codigo_ibge", "distribuidora"]]
        .dropna(subset=["distribuidora"])
        .query("distribuidora != ''")
        .drop_duplicates("codigo_ibge")
        .copy()
    )
    df["distribuidora"] = df["distribuidora"].str.upper()
    df.to_csv(_DIST_CACHE, index=False, encoding="utf-8")
    logger.info("Cache distribuidoras salvo: %d municípios → %s", len(df), _DIST_CACHE.name)


def _calcular_lacunas(
    df_municipios_ibge: pd.DataFrame,
    df_pop: pd.DataFrame,
    codigos_dataset: set[str],
    logger: logging.Logger,
) -> pd.DataFrame:
    """Retorna municípios do IBGE sem nenhum consumidor ACL, com sua população."""
    df = df_municipios_ibge[
        ~df_municipios_ibge["codigo_ibge"].isin(codigos_dataset)
    ][["codigo_ibge", "nome", "uf_norm"]].copy()

    df_p = df_pop[["codigo_ibge", "populacao"]].copy()
    df_p["codigo_ibge"] = df_p["codigo_ibge"].astype(str).str.zfill(7)
    df = df.merge(df_p, on="codigo_ibge", how="left")
    df = df[df["populacao"].notna() & (df["populacao"] > 0)].copy()
    logger.info(
        "Lacunas: %d municípios sem consumidores ACL (de %d no IBGE)",
        len(df), len(df_municipios_ibge),
    )
    return df


# ─── FORMATAÇÃO ───────────────────────────────────────────────────────────────

def _br(valor: float, decimais: int = 2) -> str:
    """Formata número no padrão brasileiro (ponto milhar, vírgula decimal)."""
    fmt = f"{valor:,.{decimais}f}"
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_gwh(v: float) -> str:
    return _br(v, 2) + " GWh"

def _fmt_mwh(v: float) -> str:
    return _br(v, 1) + " MWh"

def _fmt_mwh_hab(v: float) -> str:
    return _br(v, 3) + " MWh/hab"

def _fmt_cons_100k(v: float) -> str:
    return _br(v, 1) + " por 100k hab"

def _fmt_pop(v: float) -> str:
    return _br(int(v), 0) + " hab"

def _rotulo_mes(mes_ref: str) -> str:
    meses = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
             "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
    try:
        ano, m = int(str(mes_ref)[:4]), int(str(mes_ref)[4:6])
        return f"{meses[m-1]}/{ano}"
    except Exception:
        return str(mes_ref)


# ─── MAPAS ────────────────────────────────────────────────────────────────────

def _geo_layout() -> dict:
    return dict(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")


def _fig_layout(titulo: str) -> dict:
    return dict(
        coloraxis_colorbar=dict(
            thickness=15, len=0.75, tickformat=",.2f",
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#E2E2E2", borderwidth=1,
        ),
        margin={"r": 10, "t": 60, "l": 10, "b": 10},
        paper_bgcolor="#FFFFFF",
        geo_showframe=False,
        font=dict(family='"General Sans", Calibri, Arial, sans-serif', size=12, color="#1C1C1C"),
        height=640,
        title_font=dict(
            family='"Epilogue", Arial, Helvetica, sans-serif',
            size=14, color="#013D1A",
        ),
    )


def _mapa_estados(df: pd.DataFrame, geojson: dict, mes: str) -> str:
    """Retorna HTML string — libera figura da memória antes de retornar."""
    rotulo = _rotulo_mes(mes)
    df = df.copy()
    df["hover"] = (
        "<b>" + df["uf"] + "</b><br>"
        + "Consumo ACL: " + df["consumo_total_gwh"].apply(_fmt_gwh) + "<br>"
        + "Consumo ACL: " + df["consumo_total_mwh"].apply(_fmt_mwh) + "<br>"
        + "Consumidores: " + df["n_consumidores"].apply(lambda x: _br(int(x), 0))
    )
    fig = px.choropleth(
        df, geojson=geojson, locations="uf", featureidkey="properties.sigla",
        color="consumo_total_gwh", color_continuous_scale=_COLORSCALE_GRUGEEN,
        hover_name="uf", custom_data=["hover"],
        labels={"consumo_total_gwh": "GWh"},
        title=f"CONSUMO TOTAL ACL POR ESTADO — {rotulo}",
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="white", marker_line_width=0.5,
    )
    fig.update_geos(**_geo_layout())
    fig.update_layout(**_fig_layout("Estado"))
    fig.update_layout(coloraxis_colorbar_title="GWh")
    html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    del fig
    gc.collect()
    return html


def _mapa_municipios_coro(
    df: pd.DataFrame,
    geojson_path: Path,
    mes: str,
    coluna_cor: str,
    titulo: str,
    label_cb: str,
    fmt_hover: Callable,
    logger: logging.Logger,
    colorscale: list | str = _COLORSCALE_GRUGEEN,
    linha_extra_hover: str | None = None,
    df_vazios: pd.DataFrame | None = None,
    geojson_vazios_path: Path | None = None,
    use_log_scale: bool = False,
) -> str:
    """
    Coroplético genérico por município.
    Carrega o GeoJSON do disco e deleta da memória após serializar o HTML,
    evitando acumular múltiplas cópias grandes simultaneamente.
    """
    logger.info("  Carregando GeoJSON (%s) ...", geojson_path.name)
    with open(geojson_path, encoding="utf-8") as f:
        geojson = json.load(f)

    rotulo = _rotulo_mes(mes)

    # Municípios com ACL mas sem dado per-capita (ex: pop. não encontrada no Censo)
    # Precisam de tratamento explícito; se ignorados ficam em branco no mapa.
    df_sem_dados = df[
        df[coluna_cor].isna() & df["codigo_ibge"].notna()
    ].copy() if "codigo_ibge" in df.columns else pd.DataFrame()

    df = df[df[coluna_cor].notna() & (df[coluna_cor] > 0)].copy()
    df["label"] = df["cidade"].str.title() + " — " + df["uf"]
    df["hover_val"] = df[coluna_cor].apply(fmt_hover)

    # Aplica transformação logarítmica para reduzir disparidade visual entre municípios
    coluna_plot = coluna_cor
    range_cor = None
    if use_log_scale:
        coluna_plot = f"__{coluna_cor}_log"
        df[coluna_plot] = np.log1p(df[coluna_cor])
        range_cor = (0.0, float(df[coluna_plot].max()))

    linhas_hover = (
        "<b>" + df["label"] + "</b><br>"
        + label_cb + ": " + df["hover_val"] + "<br>"
    )
    if linha_extra_hover and linha_extra_hover in df.columns:
        df["_extra"] = df[linha_extra_hover]
        if linha_extra_hora_fmt := _hover_formatters.get(linha_extra_hover):
            df["_extra_fmt"] = df["_extra"].apply(linha_extra_hora_fmt)
        else:
            df["_extra_fmt"] = df["_extra"].astype(str)
        linhas_hover = linhas_hover + "(" + df["_extra_fmt"] + ")<br>"

    linhas_hover = linhas_hover + "Consumidores: " + df["n_consumidores"].apply(lambda x: _br(int(x), 0))
    if "populacao" in df.columns:
        linhas_hover = linhas_hover + "<br>Habitantes: " + df["populacao"].apply(
            lambda x: _br(int(x), 0) if pd.notna(x) and x > 0 else "n/d"
        )
    df["hover"] = linhas_hover

    logger.info("  Renderizando '%s' ...", titulo)
    fig = px.choropleth(
        df, geojson=geojson, locations="codigo_ibge",
        featureidkey="properties.codarea",
        color=coluna_plot, color_continuous_scale=colorscale,
        hover_name="label", custom_data=["hover"],
        labels={coluna_plot: label_cb},
        title=titulo.upper() + f" — {rotulo}",
        range_color=range_cor,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="rgba(255,255,255,0.4)", marker_line_width=0.3,
    )
    fig.update_geos(**_geo_layout())
    fig.update_layout(**_fig_layout(titulo))

    if use_log_scale:
        # Substitui ticks do colorbar: eixo em log, rótulos em valores originais
        log_max = float(df[coluna_plot].max())
        tick_vals_log = [i * log_max / 5 for i in range(6)]
        tick_texts = [fmt_hover(float(np.expm1(v))) for v in tick_vals_log]
        fig.update_layout(coloraxis_colorbar=dict(
            thickness=15, len=0.75,
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#E2E2E2", borderwidth=1,
            tickvals=tick_vals_log,
            ticktext=tick_texts,
            title=f"{label_cb}<br><sup>escala log</sup>",
        ))
    else:
        fig.update_layout(coloraxis_colorbar_title=label_cb)

    # Municípios com ACL mas sem dado per-capita: renderiza em cinza-âmbar distinto
    if len(df_sem_dados) > 0:
        df_sd = df_sem_dados.copy()
        df_sd["_lbl"] = df_sd["cidade"].str.title() + " — " + df_sd["uf"]
        n_cons = df_sd["n_consumidores"].apply(lambda x: _br(int(x), 0))
        hover_sd = (
            "<b>" + df_sd["_lbl"] + "</b><br>"
            + "Consumidores ACL: " + n_cons + "<br>"
            + "Sem dados populacionais (Censo 2022)"
        )
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=df_sd["codigo_ibge"].tolist(),
            z=[0] * len(df_sd),
            featureidkey="properties.codarea",
            colorscale=[[0, "#C8BFB8"], [1, "#C8BFB8"]],
            customdata=hover_sd.tolist(),
            hovertemplate="%{customdata}<extra></extra>",
            marker_line_color="rgba(255,255,255,0.4)",
            marker_line_width=0.3,
            showscale=False,
            showlegend=False,
            name="Sem dados pop.",
        ))
        logger.info("  %d municípios sem dados per-capita (cinza-âmbar)", len(df_sd))

    # Detecta features do GeoJSON sem cobertura em nenhum trace (cache stale residual)
    codigos_cobertos = set(df["codigo_ibge"].dropna().astype(str).str.zfill(7)) if "codigo_ibge" in df.columns else set()
    if len(df_sem_dados) > 0 and "codigo_ibge" in df_sem_dados.columns:
        codigos_cobertos |= set(df_sem_dados["codigo_ibge"].dropna().astype(str).str.zfill(7))
    codigos_geojson = {
        str(feat.get("properties", {}).get("codarea", "")).strip()
        for feat in geojson.get("features", [])
        if feat.get("properties", {}).get("codarea")
    }
    codigos_orfaos = list(codigos_geojson - codigos_cobertos)
    if codigos_orfaos:
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=codigos_orfaos,
            z=[0] * len(codigos_orfaos),
            featureidkey="properties.codarea",
            colorscale=[[0, "#CECECE"], [1, "#CECECE"]],
            text=["Sem dados neste período"] * len(codigos_orfaos),
            hovertemplate="%{text}<extra></extra>",
            marker_line_color="rgba(255,255,255,0.4)",
            marker_line_width=0.3,
            showscale=False,
            showlegend=False,
            name="Sem dados",
        ))
        logger.info("  %d municípios órfãos cobertos (cache stale)", len(codigos_orfaos))

    if df_vazios is not None and geojson_vazios_path is not None and len(df_vazios) > 0:
        logger.info("  Carregando GeoJSON vazios (%s) ...", geojson_vazios_path.name)
        with open(geojson_vazios_path, encoding="utf-8") as fv:
            geojson_vazios = json.load(fv)
        df_v = df_vazios.copy()
        df_v["_lbl"] = df_v["nome"].str.title() + " — " + df_v["uf_norm"]
        hover_v = (
            "<b>" + df_v["_lbl"] + "</b><br>"
            + "Habitantes: " + df_v["populacao"].apply(
                lambda x: _br(int(x), 0) if pd.notna(x) and x > 0 else "n/d"
            ) + "<br>Sem consumidores no ACL"
        )
        fig.add_trace(go.Choropleth(
            geojson=geojson_vazios,
            locations=df_v["codigo_ibge"].tolist(),
            z=[0] * len(df_v),
            featureidkey="properties.codarea",
            colorscale=[[0, "#CECECE"], [1, "#CECECE"]],
            customdata=hover_v.tolist(),
            hovertemplate="%{customdata}<extra></extra>",
            marker_line_color="rgba(255,255,255,0.4)",
            marker_line_width=0.3,
            showscale=False,
            showlegend=False,
            name="Sem ACL",
        ))
        del geojson_vazios

    logger.info("  Serializando HTML ...")
    html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    del fig, geojson
    gc.collect()
    logger.info("  OK (%.1f MB HTML)", len(html) / 1024**2)
    return html


def _mapa_lacunas(
    df: pd.DataFrame,
    geojson_path: Path,
    mes: str,
    logger: logging.Logger,
    df_acl: pd.DataFrame | None = None,
    geojson_acl_path: Path | None = None,
) -> str:
    """Coroplético de municípios SEM consumidores ACL, colorido por população."""
    logger.info("  Carregando GeoJSON (%s) ...", geojson_path.name)
    with open(geojson_path, encoding="utf-8") as f:
        geojson = json.load(f)

    rotulo = _rotulo_mes(mes)
    df = df[df["populacao"].notna() & (df["populacao"] > 0)].copy()
    df["label"] = df["nome"].str.title() + " — " + df["uf_norm"]
    df["hover"] = (
        "<b>" + df["label"] + "</b><br>"
        + "Habitantes: " + df["populacao"].apply(lambda x: _br(int(x), 0)) + "<br>"
        + "Sem consumidores no ACL"
    )

    titulo = f"LACUNAS DE MERCADO — MUNICÍPIOS SEM CONSUMIDORES ACL — {rotulo}"
    logger.info("  Renderizando mapa de lacunas (%d municípios) ...", len(df))
    fig = px.choropleth(
        df, geojson=geojson, locations="codigo_ibge",
        featureidkey="properties.codarea",
        color="populacao", color_continuous_scale=_COLORSCALE_LACUNAS,
        hover_name="label", custom_data=["hover"],
        labels={"populacao": "Habitantes"},
        title=titulo,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="rgba(255,255,255,0.4)", marker_line_width=0.3,
    )
    fig.update_geos(**_geo_layout())
    fig.update_layout(**_fig_layout("Lacunas"))
    fig.update_layout(coloraxis_colorbar_title="Habitantes")

    if df_acl is not None and geojson_acl_path is not None and len(df_acl) > 0:
        logger.info("  Carregando GeoJSON ACL (%s) ...", geojson_acl_path.name)
        with open(geojson_acl_path, encoding="utf-8") as fa:
            geojson_acl = json.load(fa)
        df_a = df_acl[df_acl["consumo_total_gwh"].notna() & (df_acl["consumo_total_gwh"] > 0)].copy()
        df_a["_lbl"] = df_a["cidade"].str.title() + " — " + df_a["uf"]
        hover_a = (
            "<b>" + df_a["_lbl"] + "</b><br>"
            + "Consumo ACL: " + df_a["consumo_total_gwh"].apply(_fmt_gwh) + "<br>"
            + "Consumidores: " + df_a["n_consumidores"].apply(lambda x: _br(int(x), 0)) + "<br>"
            + "Possui consumidores no ACL"
        )
        fig.add_trace(go.Choropleth(
            geojson=geojson_acl,
            locations=df_a["codigo_ibge"].tolist(),
            z=[0] * len(df_a),
            featureidkey="properties.codarea",
            colorscale=[[0, "#CECECE"], [1, "#CECECE"]],
            customdata=hover_a.tolist(),
            hovertemplate="%{customdata}<extra></extra>",
            marker_line_color="rgba(255,255,255,0.4)",
            marker_line_width=0.3,
            showscale=False,
            showlegend=False,
            name="Com ACL",
        ))
        del geojson_acl

    logger.info("  Serializando HTML ...")
    html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    del fig, geojson
    gc.collect()
    logger.info("  OK (%.1f MB HTML)", len(html) / 1024**2)
    return html


# Mapeamento de formatadores para colunas extras no hover
_hover_formatters: dict[str, Callable] = {
    "consumo_total_gwh": _fmt_gwh,
    "consumo_total_mwh": _fmt_mwh,
    "mwh_por_habitante": _fmt_mwh_hab,
    "consumidores_por_100k": _fmt_cons_100k,
    "populacao": _fmt_pop,
}


def _preparar_filtro_dados_consumo(
    df_per_capita: pd.DataFrame,
    geojson_mun_path: Path,
    geojson_lac_path: Path,
    logger: logging.Logger,
) -> dict:
    """Serializa dados compactos para filtros JavaScript (Região, UF, Concessionária)."""
    import math
    logger.info("Preparando dados de filtro consumo ...")

    # All geojson codes (ACL + lacunas)
    all_codes: list[str] = []
    for gj_path in [geojson_mun_path, geojson_lac_path]:
        if gj_path.exists():
            with open(gj_path, encoding="utf-8") as f:
                gj = json.load(f)
            for feat in gj.get("features", []):
                code = str(feat.get("properties", {}).get("codarea", "")).zfill(7)
                if code and code != "0000000":
                    all_codes.append(code)
            del gj

    # Distribuidoras únicas (sorted)
    distribuidoras: list[str] = []
    if "distribuidora" in df_per_capita.columns:
        distribuidoras = sorted(
            df_per_capita["distribuidora"].dropna().unique().tolist()
        )
        distribuidoras = [d for d in distribuidoras if d]

    # Per-tab per-municipality data — one entry per (mes, ibge)
    # Use the most recent MES only for the filter data (JS will handle per-tab)
    mes_list = sorted(df_per_capita["MES_REFERENCIA"].unique().tolist())
    tabs: dict[str, dict] = {}
    for mes in mes_list:
        mes_str = str(mes)
        df_mes = df_per_capita[df_per_capita["MES_REFERENCIA"] == mes].copy()
        df_mes["consumo_total_gwh"] = df_mes["consumo_total_mwh"] / 1_000

        for tab_id, val_col in [
            ("municipio", "consumo_total_gwh"),
            ("mwh-hab",   "mwh_por_habitante"),
            ("cons-100k", "consumidores_por_100k"),
        ]:
            mun_data: dict[str, dict] = {}
            for _, row in df_mes.iterrows():
                ibge = str(row.get("codigo_ibge", "")).zfill(7)
                if not ibge or ibge == "0000000":
                    continue
                v = float(row.get(val_col) or 0) if not (
                    isinstance(row.get(val_col), float) and math.isnan(row.get(val_col))
                ) else 0.0
                if v <= 0:
                    continue
                pop = float(row.get("populacao") or 0)
                gwh = float(row.get("consumo_total_gwh") or 0)
                d: dict = {
                    "uf":   str(row.get("uf", "")),
                    "reg":  str(row.get("regiao", "")),
                    "dist": str(row.get("distribuidora", "") or ""),
                    "v":    round(v, 6),
                    "lv":   round(float(np.log1p(v)), 6),
                    "nome": str(row.get("cidade", "")).title(),
                    "gwh":  round(gwh, 4),
                    "nc":   int(row.get("n_consumidores") or 0),
                    "pop":  int(pop) if pop > 0 else 0,
                }
                mun_data[ibge] = d
            log_max = float(np.log1p(max((d["v"] for d in mun_data.values()), default=1)))
            key = f"{tab_id}_{mes_str}"
            tabs[key] = {"munData": mun_data, "logMax": round(log_max, 6), "mes": mes_str, "tab": tab_id}

    logger.info("  Filtro consumo: %d meses × 3 abas", len(mes_list))
    return {
        "reg":    _UF_REGIAO,
        "ufs":    sorted(_UF_PARA_IBGE.keys()),
        "dists":  distribuidoras,
        "meses":  [str(m) for m in mes_list],
        "allCodes": all_codes,
        "tabs":   tabs,
    }


def _gerar_tabela_html(
    df: pd.DataFrame,
    colunas: list[tuple[str, str, Callable | None]],
    ibge_col: str = "codigo_ibge",
) -> str:
    """
    Gera string HTML de tabela interativa (filtro + ordenação por coluna).
    colunas: [(col_df, header_display, fmt_fn)] — fmt_fn=None → coluna texto;
    fmt_fn != None → coluna numérica (armazena data-value para ordenação).
    """
    thead_cells = "".join(
        f'<th onclick="sortTable(this)" data-col="{i}">'
        f'{hdr} <span class="sort-arrow">&#x21C5;</span></th>'
        for i, (_, hdr, _) in enumerate(colunas)
    )
    thead = f"<tr>{thead_cells}</tr>"

    rows_html: list[str] = []
    for _, row in df.iterrows():
        ibge = str(row.get(ibge_col, "")).zfill(7) if ibge_col in df.columns else ""
        cells = []
        for col, _, fmt_fn in colunas:
            val = row.get(col)
            if fmt_fn is not None and pd.notna(val):
                cells.append(f'<td data-value="{val}">{fmt_fn(val)}</td>')
            else:
                cells.append(f'<td>{val if pd.notna(val) else ""}</td>')
        rows_html.append(f'<tr data-ibge="{ibge}">' + "".join(cells) + "</tr>")

    total = len(rows_html)
    tbody = "\n".join(rows_html)
    return (
        '<div class="table-controls">'
        '<input type="text" class="table-filter" placeholder="Filtrar..." oninput="filterTable(this)">'
        f'<span class="table-count">{total} linhas</span>'
        '</div>'
        '<div class="table-wrapper">'
        f'<table class="data-table"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'
        '</div>'
    )


# ─── DASHBOARD HTML ───────────────────────────────────────────────────────────

def _salvar_dashboard(
    figs: dict[str, tuple[str, str, str]],
    mes: str,
    logger: logging.Logger,
    filtro_dados: dict | None = None,
) -> Path:
    """
    Salva todas as figuras e tabelas num único HTML com sistema de abas.
    figs: {tab_id: (html_fig, html_table, "Label da aba")}
    """
    rotulo = _rotulo_mes(mes)
    logo_uri = _logo_data_uri()
    logo_tag = (
        f'<img src="{logo_uri}" alt="Grugeen" class="header-logo">'
        if logo_uri else
        '<span class="header-brand-text">GRUGEEN</span>'
    )

    tabs_html = ""
    panels_html = ""
    for i, (tab_id, (html_fig, html_table, label)) in enumerate(figs.items()):
        active = "active" if i == 0 else ""
        tabs_html += (
            f'<button class="tab-btn {active}" '
            f'onclick="showTab(\'{tab_id}\',this)">{label}</button>\n'
        )
        panels_html += (
            f'<div id="tab-{tab_id}" class="tab-panel {active}">\n'
            f'  <div class="view-controls">\n'
            f'    <button class="view-btn active" onclick="toggleView(\'{tab_id}\',\'map\',this)">&#128506; Mapa</button>\n'
            f'    <button class="view-btn" onclick="toggleView(\'{tab_id}\',\'table\',this)">&#128203; Tabela</button>\n'
            f'  </div>\n'
            f'  <div class="view-map">{html_fig}</div>\n'
            f'  <div class="view-table">{html_table}</div>\n'
            f'</div>\n'
        )

    # Serialize filter data
    import math as _math
    def _clean_fd(obj):
        if isinstance(obj, float):
            return None if (_math.isnan(obj) or _math.isinf(obj)) else obj
        if isinstance(obj, dict):
            return {k: _clean_fd(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean_fd(v) for v in obj]
        return obj

    fd_json = "null"
    dist_sel_html = ""
    if filtro_dados is not None:
        fd_json = json.dumps(_clean_fd(filtro_dados), ensure_ascii=False, separators=(",", ":"))
        if filtro_dados.get("dists"):
            opts = "".join(f'<option value="{d}">{d}</option>' for d in filtro_dados["dists"])
            dist_sel_html = (
                f'<select class="filter-sel" id="fil-dist" onchange="applyFilters()" '
                f'title="Filtrar por concessionária distribuidora">'
                f'<option value="">Todas as distribuidoras</option>{opts}</select>'
            )

    template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Consumo ACL — {rotulo} | Grugeen</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Epilogue:wght@600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --verde:        #1D683C;
      --verde-escuro: #013D1A;
      --grafite:      #1C1C1C;
      --offwhite:     #E2E2E2;
      --cinza:        #A6A6A6;
      --laranja:      #EC6C41;
      --font-heading: "Epilogue", Arial, Helvetica, sans-serif;
      --font-body:    "General Sans", Calibri, Arial, sans-serif;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; }}
    body {{
      font-family: var(--font-body);
      background: var(--offwhite);
      color: var(--grafite);
      display: flex; flex-direction: column; min-height: 100vh;
    }}
    header {{
      background: var(--verde-escuro);
      border-bottom: 3px solid var(--verde);
      padding: 12px 28px;
      flex-shrink: 0;
      display: flex; align-items: center; gap: 20px;
    }}
    .header-logo {{ height: 36px; width: auto; flex-shrink: 0; }}
    .header-brand-text {{
      font-family: var(--font-heading); font-weight: 700;
      font-size: 1.2rem; text-transform: uppercase;
      letter-spacing: 0.1em; color: var(--offwhite); flex-shrink: 0;
    }}
    .header-divider {{
      width: 1px; height: 30px; background: rgba(226,226,226,0.25); flex-shrink: 0;
    }}
    .header-info {{ flex: 1; }}
    .header-info h1 {{
      font-family: var(--font-heading); font-weight: 600; font-size: 0.95rem;
      text-transform: uppercase; letter-spacing: 0.05em; color: var(--offwhite);
    }}
    .header-info p {{
      font-family: var(--font-body); font-size: 0.75rem;
      color: var(--cinza); margin-top: 3px;
    }}
    .note {{
      padding: 5px 28px; font-size: 0.72rem;
      color: var(--grafite); background: #fff;
      border-bottom: 1px solid var(--offwhite); flex-shrink: 0;
    }}
    .tabs {{
      display: flex; flex-wrap: wrap; gap: 2px; padding: 10px 20px 0;
      background: var(--offwhite); flex-shrink: 0;
    }}
    .tab-btn {{
      padding: 7px 20px; border: none; border-radius: 6px 6px 0 0;
      cursor: pointer; font-family: var(--font-body);
      font-size: 0.82rem; font-weight: 600;
      background: #c4d1c6; color: var(--grafite);
      transition: background 0.15s, color 0.15s;
    }}
    .tab-btn.active {{
      background: #fff; color: var(--verde-escuro);
      border-top: 2px solid var(--verde);
    }}
    .tab-btn:hover:not(.active) {{ background: #b4c5b8; }}
    .tab-panel {{ display: none; flex: 1; background: #fff; }}
    .tab-panel.active {{ display: flex; flex-direction: column; }}
    /* ── Toggle Mapa / Tabela ─── */
    .view-controls {{
      display: flex; gap: 6px; padding: 6px 10px;
      background: #f4f7f4; border-bottom: 1px solid var(--offwhite); flex-shrink: 0;
    }}
    .view-btn {{
      padding: 4px 14px; border: 1px solid var(--cinza); border-radius: 4px;
      cursor: pointer; font-family: var(--font-body); font-size: 0.78rem; font-weight: 600;
      background: #fff; color: var(--grafite); transition: background 0.15s, color 0.15s;
    }}
    .view-btn.active {{ background: var(--verde); color: #fff; border-color: var(--verde); }}
    .view-btn:hover:not(.active) {{ background: var(--offwhite); }}
    /* ── Mapa ─── */
    .view-map {{ flex: 1; padding: 4px 8px 8px; }}
    .view-map > div {{ flex: 1 !important; min-height: 640px; }}
    .view-map > div > div {{ height: 100% !important; }}
    /* ── Tabela ─── */
    .view-table {{
      display: none; flex-direction: column; padding: 14px 16px; overflow: hidden;
    }}
    .table-controls {{
      display: flex; align-items: center; gap: 12px; margin-bottom: 10px; flex-shrink: 0;
    }}
    .table-filter {{
      padding: 6px 12px; border: 1px solid var(--cinza); border-radius: 4px;
      font-family: var(--font-body); font-size: 0.85rem; width: 300px; outline: none;
    }}
    .table-filter:focus {{ border-color: var(--verde); box-shadow: 0 0 0 2px rgba(29,104,60,0.15); }}
    .table-count {{ font-size: 0.78rem; color: var(--cinza); }}
    .table-wrapper {{
      overflow: auto; max-height: 620px;
      border: 1px solid var(--offwhite); border-radius: 4px;
    }}
    .data-table {{
      width: 100%; border-collapse: collapse;
      font-family: var(--font-body); font-size: 0.82rem;
    }}
    .data-table thead th {{
      background: var(--verde); color: #fff;
      padding: 9px 14px; text-align: left;
      font-family: var(--font-heading); font-size: 0.74rem;
      text-transform: uppercase; letter-spacing: 0.04em;
      cursor: pointer; white-space: nowrap; user-select: none;
      position: sticky; top: 0; z-index: 1;
    }}
    .data-table thead th:hover {{ background: var(--verde-escuro); }}
    .data-table tbody tr:nth-child(even) {{ background: #f6fbf8; }}
    .data-table tbody tr:hover {{ background: #dff0e7; }}
    .data-table td {{
      padding: 7px 14px; border-bottom: 1px solid var(--offwhite); white-space: nowrap;
    }}
    .sort-arrow {{ opacity: 0.55; margin-left: 5px; font-size: 0.85em; }}
    /* ── Filtros ─── */
    .filter-bar {{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 20px;background:#eef3ef;border-bottom:2px solid var(--offwhite);flex-shrink:0}}
    .filter-label {{font-family:var(--font-heading);font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--verde-escuro);white-space:nowrap}}
    .filter-sel {{padding:5px 10px;border:1px solid #bfcfc3;border-radius:4px;font-family:var(--font-body);font-size:.8rem;color:var(--grafite);background:#fff;outline:none;cursor:pointer;max-width:240px;min-width:140px}}
    .filter-sel:focus {{border-color:var(--verde);box-shadow:0 0 0 2px rgba(29,104,60,.12)}}
    .filter-clear {{padding:5px 12px;border:1px solid #bfcfc3;border-radius:4px;font-family:var(--font-body);font-size:.78rem;font-weight:600;background:#fff;color:var(--grafite);cursor:pointer;transition:background .15s}}
    .filter-clear:hover {{background:var(--offwhite)}}
    .filter-count {{font-size:.75rem;color:var(--cinza);margin-left:4px;white-space:nowrap}}
    footer {{
      background: var(--verde-escuro); color: var(--cinza);
      font-family: var(--font-body); font-size: 0.68rem;
      text-align: center; padding: 6px; flex-shrink: 0;
    }}
  </style>
</head>
<body>
  <header>
    {logo_tag}
    <div class="header-divider"></div>
    <div class="header-info">
      <h1>Consumo de Energia — Mercado Livre (ACL)</h1>
      <p>Referência: {rotulo} &nbsp;·&nbsp; CCEE Dados Abertos &nbsp;·&nbsp; Fonte populacional: IBGE Censo 2022</p>
    </div>
  </header>
  <div class="note">
    GWh = gigawatt-hora &nbsp;·&nbsp; MWh/hab = megawatt-hora por habitante &nbsp;·&nbsp;
    Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}
  </div>
  <!-- Barra de filtros -->
  <div class="filter-bar" id="filter-bar">
    <span class="filter-label">&#9660; Filtrar:</span>
    <select class="filter-sel" id="fil-regiao" onchange="onRegiaoChange()" title="Filtrar por região geográfica">
      <option value="">Todas as regiões</option>
      <option>Norte</option><option>Nordeste</option>
      <option>Centro-Oeste</option><option>Sudeste</option><option>Sul</option>
    </select>
    <select class="filter-sel" id="fil-uf" onchange="applyFilters()" title="Filtrar por estado (UF)">
      <option value="">Todos os estados</option>
    </select>
    {dist_sel_html}
    <button class="filter-clear" onclick="clearFilters()" title="Remover todos os filtros">&#10005; Limpar</button>
    <span class="filter-count" id="filter-count"></span>
  </div>
  <div class="tabs">
    {tabs_html}
  </div>
  {panels_html}
  <footer>Grugeen Consultoria Ltda &nbsp;·&nbsp; Dados: CCEE Dados Abertos &nbsp;·&nbsp; {datetime.now().year}</footer>
  <script>window._FD_C={fd_json};</script>
  <script>
    /* ── Inicialização ─── */
    (function(){{
      var fd=window._FD_C;if(!fd)return;
      var uSel=document.getElementById('fil-uf');
      fd.ufs.forEach(function(u){{uSel.add(new Option(u,u))}});
    }})();

    /* ── Navegação entre abas ─── */
    function showTab(name, btn) {{
      document.querySelectorAll('.tab-panel').forEach(function(p){{p.classList.remove('active')}});
      document.querySelectorAll('.tab-btn').forEach(function(b){{b.classList.remove('active')}});
      var panel = document.getElementById('tab-' + name);
      panel.classList.add('active');
      btn.classList.add('active');
      panel.querySelectorAll('.plotly-graph-div').forEach(function(d) {{
        if (d.layout) Plotly.relayout(d, {{autosize: true}});
      }});
      applyFilters();
    }}
    function toggleView(tabId, view, btn) {{
      var panel = document.getElementById('tab-' + tabId);
      panel.querySelector('.view-map').style.display = view === 'map' ? 'block' : 'none';
      var tbl = panel.querySelector('.view-table');
      tbl.style.display = view === 'table' ? 'flex' : 'none';
      panel.querySelectorAll('.view-btn').forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      if (view === 'map') {{
        panel.querySelectorAll('.plotly-graph-div').forEach(function(d) {{
          if (d.layout) Plotly.relayout(d, {{autosize: true}});
        }});
      }}
    }}

    /* ── Filtros ─── */
    function onRegiaoChange(){{
      var fd=window._FD_C;if(!fd)return;
      var regVal=document.getElementById('fil-regiao').value;
      var uSel=document.getElementById('fil-uf');
      var prev=uSel.value;
      while(uSel.options.length>1)uSel.remove(1);
      var ufs=regVal?fd.reg[regVal]:fd.ufs;
      ufs.forEach(function(u){{uSel.add(new Option(u,u))}});
      if(ufs.indexOf(prev)>-1)uSel.value=prev;
      applyFilters();
    }}
    function clearFilters(){{
      document.getElementById('fil-regiao').value='';
      document.getElementById('fil-uf').value='';
      var dSel=document.getElementById('fil-dist');if(dSel)dSel.value='';
      onRegiaoChange();
    }}
    function applyFilters(){{
      var fd=window._FD_C;if(!fd)return;
      var regVal=document.getElementById('fil-regiao').value;
      var ufVal=document.getElementById('fil-uf').value;
      var dSel=document.getElementById('fil-dist');
      var distVal=dSel?dSel.value:'';
      var activePanel=document.querySelector('.tab-panel.active');
      if(!activePanel)return;
      var tabId=activePanel.id.replace('tab-','');
      _applyToTab(tabId,regVal,ufVal,distVal);
    }}

    function _fGWh(v){{return (v||0).toLocaleString('pt-BR',{{minimumFractionDigits:2,maximumFractionDigits:2}})+' GWh'}}
    function _fMWH(v){{return (v||0).toLocaleString('pt-BR',{{minimumFractionDigits:1,maximumFractionDigits:1}})+' MWh/hab'}}
    function _fC100(v){{return (v||0).toLocaleString('pt-BR',{{minimumFractionDigits:1,maximumFractionDigits:1}})+' por 100k hab'}}
    function _fPop(v){{return v>0?Math.round(v).toLocaleString('pt-BR')+' hab':'n/d'}}

    function _hoverC(d,tid,v){{
      var L='<b>'+d.nome+' — '+d.uf+'</b><br>';
      var C='<br>Consumidores: '+Math.round(d.nc||0).toLocaleString('pt-BR');
      var P=(d.pop||0)>0?'<br>Habitantes: '+_fPop(d.pop):'';
      if(tid==='municipio')return L+'Consumo ACL: '+_fGWh(v)+C+P;
      if(tid==='mwh-hab')return L+'MWh/habitante: '+_fMWH(v)+'<br>Consumo total: '+_fGWh(d.gwh||0)+C+P;
      if(tid==='cons-100k')return L+'Consumidores/100k: '+_fC100(v)+C+P;
      return L+String(v);
    }}

    /* ── Bounding boxes por UF / Região ─── */
    var _BBOX={{
      'Norte':       {{lat:[-10.5,5.5],  lon:[-74,-44]}},
      'Nordeste':    {{lat:[-18.5,-1],   lon:[-48,-34.5]}},
      'Centro-Oeste':{{lat:[-24.5,-6],   lon:[-61.5,-45.5]}},
      'Sudeste':     {{lat:[-25.5,-14],  lon:[-53.5,-39]}},
      'Sul':         {{lat:[-34,-21.5],  lon:[-58.5,-47.5]}},
      'AC':{{lat:[-11.2,-7.1],lon:[-74,-66.7]}},'AL':{{lat:[-10.5,-8.8],lon:[-38.3,-35.1]}},
      'AP':{{lat:[-1.3,4.4],  lon:[-52.1,-49.9]}},'AM':{{lat:[-9.8,2.3], lon:[-73.8,-56.1]}},
      'BA':{{lat:[-18.4,-8.5],lon:[-46.5,-37.4]}},'CE':{{lat:[-7.9,-2.8],lon:[-41.4,-37.3]}},
      'DF':{{lat:[-16.1,-15.5],lon:[-48.3,-47.3]}},'ES':{{lat:[-21.3,-17.9],lon:[-41.9,-39.7]}},
      'GO':{{lat:[-19.5,-12.4],lon:[-53.3,-45.9]}},'MA':{{lat:[-10.3,-1],lon:[-48.8,-41.8]}},
      'MT':{{lat:[-18.1,-7.3],lon:[-61.6,-50.2]}},'MS':{{lat:[-24.1,-17.2],lon:[-58.3,-50.9]}},
      'MG':{{lat:[-22.9,-14.2],lon:[-51,-39.9]}},'PA':{{lat:[-9.5,2.6],lon:[-58.9,-46]}},
      'PB':{{lat:[-8.3,-6],  lon:[-38.8,-34.8]}},'PR':{{lat:[-26.7,-22.5],lon:[-54.6,-48]}},
      'PE':{{lat:[-9.5,-7.3],lon:[-41.4,-34.9]}},'PI':{{lat:[-10.9,-2.8],lon:[-45.9,-40.4]}},
      'RJ':{{lat:[-23.4,-20.8],lon:[-44.9,-41]}},'RN':{{lat:[-6.9,-4.8],lon:[-38.6,-35]}},
      'RS':{{lat:[-33.8,-27.1],lon:[-57.7,-49.7]}},'RO':{{lat:[-13.7,-7.9],lon:[-66.8,-59.8]}},
      'RR':{{lat:[-1.5,5.3], lon:[-64.8,-59.8]}},'SC':{{lat:[-29.4,-25.9],lon:[-53.8,-48.4]}},
      'SP':{{lat:[-25.3,-19.8],lon:[-53.1,-44.2]}},'SE':{{lat:[-11.6,-9.5],lon:[-38.3,-36.4]}},
      'TO':{{lat:[-13.5,-5.2],lon:[-50.7,-45.7]}}
    }};
    function _zoomMap(plotDiv,regVal,ufVal){{
      var bk=ufVal||regVal;
      if(bk&&_BBOX[bk]){{
        var b=_BBOX[bk];
        Plotly.relayout(plotDiv,{{'geo.fitbounds':false,'geo.lataxis.range':b.lat,'geo.lonaxis.range':b.lon}});
      }}else{{
        Plotly.relayout(plotDiv,{{'geo.fitbounds':'locations'}});
      }}
    }}
    function _applyToTab(tabId,regVal,ufVal,distVal){{
      var fd=window._FD_C;if(!fd)return;
      /* identificar chave dos dados (mes + tab) */
      var mes='{mes}';
      var key=tabId+'_'+mes;
      var tabData=fd.tabs[key];
      /* abas sem dados de filtro (estados, lacunas) — só filtrar tabela */
      var mapTabs=['municipio','mwh-hab','cons-100k'];
      var filtUfs=ufVal?[ufVal]:(regVal?fd.reg[regVal]:null);
      var panel=document.getElementById('tab-'+tabId);if(!panel)return;

      if(tabData&&mapTabs.indexOf(tabId)>-1){{
        var locs=[],zVals=[],hoverArr=[];
        Object.keys(tabData.munData).forEach(function(ibge){{
          var d=tabData.munData[ibge];
          if(filtUfs&&filtUfs.indexOf(d.uf)===-1)return;
          if(distVal&&d.dist!==distVal)return;
          var v=d.v;if(!(v>0))return;
          locs.push(ibge);zVals.push(Math.log1p(v));hoverArr.push([_hoverC(d,tabId,v)]);
        }});
        var filtSet=new Set(locs);
        var grayCodes=fd.allCodes.filter(function(c){{return!filtSet.has(c)}});
        var plotDiv=panel.querySelector('.plotly-graph-div');
        if(plotDiv&&plotDiv.data&&plotDiv.data.length>0){{
          Plotly.restyle(plotDiv,{{locations:[locs],z:[zVals],customdata:[hoverArr]}},[0]);
          var li=plotDiv.data.length-1;
          if(li>0)Plotly.restyle(plotDiv,{{locations:[grayCodes],z:[new Array(grayCodes.length).fill(0)]}},[li]);
          _zoomMap(plotDiv,regVal,ufVal);
        }}
        var fci=document.getElementById('filter-count');
        if(fci)fci.textContent=locs.length+' município'+(locs.length!==1?'s':'');
      }}

      /* Filtrar tabela por UF e distribuidora */
      var tvEl=panel.querySelector('.view-table');
      if(tvEl){{
        var rows=tvEl.querySelectorAll('.data-table tbody tr');
        var shown=0;
        rows.forEach(function(row){{
          var rowUf=row.cells[1]?row.cells[1].textContent.trim():'';
          var show=(!filtUfs||filtUfs.indexOf(rowUf)>-1);
          if(show&&distVal){{var ri=row.dataset.ibge||'';show=!ri||(tabData&&filtSet&&filtSet.has(ri));}}
          row.style.display=show?'':'none';if(show)shown++;
        }});
        var cntEl=tvEl.querySelector('.table-count');
        if(cntEl)cntEl.textContent=shown+' de '+rows.length+' linhas';
      }}
    }}

    /* ── Filtro de texto na tabela ─── */
    function filterTable(input) {{
      var filter = input.value.toLowerCase();
      var tblView = input.closest('.view-table');
      var rows = tblView.querySelectorAll('.data-table tbody tr');
      var count = 0;
      rows.forEach(function(row) {{
        var show = row.textContent.toLowerCase().indexOf(filter) > -1;
        row.style.display = show ? '' : 'none';
        if (show) count++;
      }});
      tblView.querySelector('.table-count').textContent = count + ' de ' + rows.length + ' linhas';
    }}

    /* ── Ordenação de tabela ─── */
    var _sortDir = {{}};
    function sortTable(th) {{
      var col = parseInt(th.dataset.col);
      var table = th.closest('table');
      if (!table.id) table.id = 'tbl_' + Math.random().toString(36).slice(2);
      var key = table.id + '_' + col;
      _sortDir[key] = (_sortDir[key] || 0) === 1 ? -1 : 1;
      var dir = _sortDir[key];
      th.closest('thead').querySelectorAll('.sort-arrow').forEach(function(s) {{ s.textContent = '⇅'; }});
      th.querySelector('.sort-arrow').textContent = dir === 1 ? '↑' : '↓';
      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b) {{
        var ac = a.cells[col], bc = b.cells[col];
        var an = ac.hasAttribute('data-value') ? parseFloat(ac.dataset.value) : NaN;
        var bn = bc.hasAttribute('data-value') ? parseFloat(bc.dataset.value) : NaN;
        if (!isNaN(an) && !isNaN(bn)) return dir * (an - bn);
        return dir * ac.textContent.trim().localeCompare(bc.textContent.trim(), 'pt-BR');
      }});
      rows.forEach(function(r) {{ tbody.appendChild(r); }});
    }}
  </script>
</body>
</html>"""

    saida = PASTA_SAIDA / f"mapa_consumo_{mes}.html"
    saida.write_text(template, encoding="utf-8")
    logger.info("Dashboard salvo: %s (%.1f MB)", saida.name, saida.stat().st_size / 1024 ** 2)
    return saida


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def _prevent_sleep() -> None:
    """Impede que o Windows entre em modo de espera/hibernação durante a execução."""
    ES_CONTINUOUS     = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        pass  # não-Windows ou sem permissão — ignora silenciosamente


def _restore_sleep() -> None:
    """Restaura a gestão de energia normal do Windows."""
    ES_CONTINUOUS = 0x80000000
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


def main() -> None:
    logger = _setup_logging()
    PASTA_SAIDA.mkdir(exist_ok=True)

    if not ARQUIVO_ENTRADA.exists():
        logger.error("Arquivo não encontrado: %s", ARQUIVO_ENTRADA)
        sys.exit(1)

    _prevent_sleep()
    logger.info("Modo de espera do Windows desativado durante a execução.")

    logger.info("=" * 65)
    logger.info("Mapa Interativo de Consumo Mensal — CCEE Dados Abertos")
    logger.info("Entrada: %s (%.0f MB)", ARQUIVO_ENTRADA.name,
                ARQUIVO_ENTRADA.stat().st_size / 1024 ** 2)
    logger.info("=" * 65)

    t_total = time.perf_counter()

    try:
        # 1. Agrega dados com DuckDB (~20 s para 34 M linhas)
        df_estados = _agregar_por_estado(logger)
        df_cidades = _agregar_por_cidade(logger)

        # 2. GeoJSON de estados (pequeno — mantido em memória)
        _baixar_recurso(_GEOJSON_EST_URL, _GEOJSON_EST_CACHE, logger)
        raw_est = _GEOJSON_EST_CACHE.read_bytes()
        if raw_est[:2] == b"\x1f\x8b":
            raw_est = gzip.decompress(raw_est)
        geojson_estados = json.loads(raw_est.decode("utf-8"))
        del raw_est

        df_municipios = _carregar_municipios(logger)

        # 3. Join nome da cidade → código IBGE + lat/lon
        df_cidades_geo = _geocodificar(df_cidades, df_municipios, logger)
        del df_cidades
        _salvar_distribuidoras_cache(df_cidades_geo, logger)

        # 4. Populacao e métricas per capita
        df_pop = _baixar_populacao(logger)
        df_per_capita = _calcular_per_capita(df_cidades_geo, df_pop, logger)

        # 5. GeoJSON de municípios + cálculo de lacunas
        codigos_dataset = set(
            df_cidades_geo["codigo_ibge"].dropna().astype(str).str.zfill(7)
        )
        codigos_todos = set(
            df_municipios["codigo_ibge"].dropna().astype(str).str.zfill(7)
        )
        codigos_ausentes = codigos_todos - codigos_dataset
        df_lacunas = _calcular_lacunas(df_municipios, df_pop, codigos_dataset, logger)
        del df_municipios, df_pop

        geojson_mun_path, geojson_lac_path = _baixar_geojson_municipios(
            codigos_dataset, codigos_ausentes, logger
        )

        # 6. Dados de filtro (Região / UF / Concessionária)
        logger.info("--- Preparando dados de filtro ---")
        filtro_dados_consumo = _preparar_filtro_dados_consumo(
            df_per_capita, geojson_mun_path, geojson_lac_path, logger
        )

        # 7. Gera dashboard por mês
        arquivos_gerados: list[Path] = []
        for mes in sorted(df_estados["MES_REFERENCIA"].unique()):
            rotulo = _rotulo_mes(str(mes))
            logger.info("--- Gerando mapas: %s ---", rotulo)

            df_e  = df_estados[df_estados["MES_REFERENCIA"] == mes]
            df_pc = df_per_capita[df_per_capita["MES_REFERENCIA"] == mes].copy()
            df_pc["consumo_total_gwh"] = df_pc["consumo_total_mwh"] / 1_000

            logger.info("[1/5] Mapa por estado ...")
            html_estados = _mapa_estados(df_e, geojson_estados, str(mes))

            logger.info("[2/5] Mapa por município (GWh) ...")
            html_municipio = _mapa_municipios_coro(
                df_pc, geojson_mun_path, str(mes),
                coluna_cor="consumo_total_gwh",
                titulo="Consumo Total ACL por Município",
                label_cb="GWh",
                fmt_hover=_fmt_gwh,
                logger=logger,
                df_vazios=df_lacunas,
                geojson_vazios_path=geojson_lac_path,
                use_log_scale=True,
            )

            logger.info("[3/5] Mapa MWh/habitante ...")
            html_mwh_hab = _mapa_municipios_coro(
                df_pc, geojson_mun_path, str(mes),
                coluna_cor="mwh_por_habitante",
                titulo="Consumo ACL por Habitante",
                label_cb="MWh/hab",
                fmt_hover=_fmt_mwh_hab,
                logger=logger,
                linha_extra_hover="consumo_total_mwh",
                df_vazios=df_lacunas,
                geojson_vazios_path=geojson_lac_path,
                use_log_scale=True,
            )

            logger.info("[4/5] Mapa consumidores/100k hab ...")
            html_cons_100k = _mapa_municipios_coro(
                df_pc, geojson_mun_path, str(mes),
                coluna_cor="consumidores_por_100k",
                titulo="Penetração ACL — Consumidores por 100.000 hab",
                label_cb="Consumidores/100k",
                fmt_hover=_fmt_cons_100k,
                logger=logger,
                linha_extra_hover="consumo_total_gwh",
                df_vazios=df_lacunas,
                geojson_vazios_path=geojson_lac_path,
                use_log_scale=True,
            )

            logger.info("[5/5] Mapa de lacunas de mercado ...")
            html_lacunas_fig = _mapa_lacunas(
                df_lacunas, geojson_lac_path, str(mes), logger,
                df_acl=df_pc, geojson_acl_path=geojson_mun_path,
            )

            logger.info("[Tabelas] Gerando visualizações tabulares ...")
            _fmt_pop_tbl = lambda x: _br(int(x), 0) if x > 0 else "n/d"

            tbl_estados = _gerar_tabela_html(
                df_e.sort_values("consumo_total_gwh", ascending=False),
                [
                    ("uf", "Estado", None),
                    ("n_consumidores", "Consumidores", lambda x: _br(int(x), 0)),
                    ("consumo_total_gwh", "Consumo (GWh)", _fmt_gwh),
                    ("consumo_total_mwh", "Consumo (MWh)", _fmt_mwh),
                ],
            )

            df_mun = df_pc[df_pc["consumo_total_gwh"].notna() & (df_pc["consumo_total_gwh"] > 0)].copy()
            df_mun["_cidade"] = df_mun["cidade"].str.title()
            tbl_municipio = _gerar_tabela_html(
                df_mun.sort_values("consumo_total_gwh", ascending=False),
                [
                    ("_cidade", "Município", None),
                    ("uf", "UF", None),
                    ("consumo_total_gwh", "Consumo (GWh)", _fmt_gwh),
                    ("n_consumidores", "Consumidores", lambda x: _br(int(x), 0)),
                    ("populacao", "Habitantes", _fmt_pop_tbl),
                ],
            )

            df_pc_hab = df_pc[df_pc["mwh_por_habitante"].notna()].copy()
            df_pc_hab["_cidade"] = df_pc_hab["cidade"].str.title()
            tbl_mwh_hab = _gerar_tabela_html(
                df_pc_hab.sort_values("mwh_por_habitante", ascending=False),
                [
                    ("_cidade", "Município", None),
                    ("uf", "UF", None),
                    ("mwh_por_habitante", "MWh/hab", _fmt_mwh_hab),
                    ("consumo_total_gwh", "Consumo (GWh)", _fmt_gwh),
                    ("n_consumidores", "Consumidores", lambda x: _br(int(x), 0)),
                    ("populacao", "Habitantes", _fmt_pop_tbl),
                ],
            )

            df_pc_100k = df_pc[df_pc["consumidores_por_100k"].notna()].copy()
            df_pc_100k["_cidade"] = df_pc_100k["cidade"].str.title()
            tbl_cons_100k = _gerar_tabela_html(
                df_pc_100k.sort_values("consumidores_por_100k", ascending=False),
                [
                    ("_cidade", "Município", None),
                    ("uf", "UF", None),
                    ("consumidores_por_100k", "Cons/100k hab", _fmt_cons_100k),
                    ("n_consumidores", "Consumidores", lambda x: _br(int(x), 0)),
                    ("populacao", "Habitantes", _fmt_pop_tbl),
                ],
            )

            tbl_lacunas = _gerar_tabela_html(
                df_lacunas.sort_values("populacao", ascending=False),
                [
                    ("nome", "Município", None),
                    ("uf_norm", "UF", None),
                    ("populacao", "Habitantes", lambda x: _br(int(x), 0)),
                ],
            )

            figs: dict[str, tuple[str, str, str]] = {
                "estados":   (html_estados,     tbl_estados,   "&#128506; Por Estado"),
                "municipio": (html_municipio,   tbl_municipio, "&#127968; Por Município"),
                "mwh-hab":   (html_mwh_hab,     tbl_mwh_hab,   "&#9889; MWh / Habitante"),
                "cons-100k": (html_cons_100k,   tbl_cons_100k, "&#128101; Consumidores / 100k hab"),
                "lacunas":   (html_lacunas_fig, tbl_lacunas,   "&#128270; Lacunas de Mercado"),
            }

            p = _salvar_dashboard(figs, str(mes), logger, filtro_dados_consumo)
            arquivos_gerados.append(p)

        logger.info("=" * 65)
        logger.info(
            "CONCLUÍDO em %.1f s | %d arquivo(s) em: %s",
            time.perf_counter() - t_total, len(arquivos_gerados), PASTA_SAIDA,
        )
        for p in arquivos_gerados:
            logger.info("  → %s", p.name)
        logger.info("=" * 65)

    finally:
        _restore_sleep()
        logger.info("Gestão de energia do Windows restaurada.")


if __name__ == "__main__":
    main()

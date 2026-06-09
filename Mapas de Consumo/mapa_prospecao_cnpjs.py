#!/usr/bin/env python3
# =============================================================================
# SCRIPT: Mapa interativo de prospecção — Concentração Industrial por Município
# Fonte: Dados Abertos CNPJ - Receita Federal (via processar_cnpjs_energia.py)
# =============================================================================
# OBJETIVO:
#   Dashboard HTML interativo com quatro visualizações de potencial de mercado:
#     1) Concentração industrial — total de empresas Tier 1 por município
#     2) Demanda potencial estimada (MW) por município
#     3) Densidade industrial — empresas Tier 1 por 1.000 habitantes
#     4) Oportunidades — municípios com alto potencial e baixa penetração ACL
#
# SAÍDA: mapas/mapa_prospecao_cnpjs.html
#
# DEPENDÊNCIAS: pandas plotly (sem duckdb — dados já estão agregados)
# CACHE: reutiliza os GeoJSONs de br_municipios gerados pelo mapa_consumo_mensal.py
# =============================================================================

import base64
import ctypes
import gc
import io
import json
import logging
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# ─── CAMINHOS ────────────────────────────────────────────────────────────────

_AQUI = Path(__file__).parent

PASTA_SAIDA   = _AQUI / "mapas"
DIR_PROSPC    = _AQUI / "Prospecção CNPJs"
DIR_RESULT    = DIR_PROSPC / "resultados"
DIR_BASES     = DIR_PROSPC / "bases"

ARQUIVO_RESUMO = DIR_RESULT / "resumo_municipio_cnae_completo.csv"

# ─── CACHE COMPARTILHADO com mapa_consumo_mensal.py ──────────────────────────

_GEOJSON_EST_CACHE = PASTA_SAIDA / "br_estados.geojson"
_GEOJSON_MUN_CACHE = PASTA_SAIDA / "br_municipios_filtrado.geojson"
_GEOJSON_LAC_CACHE = PASTA_SAIDA / "br_municipios_lacunas.geojson"
_GEOJSON_ALL_CACHE = PASTA_SAIDA / "br_municipios_todos.geojson"
_MUNICIPIOS_CACHE  = PASTA_SAIDA / "municipios_ibge.csv"
_POPULACAO_CACHE   = PASTA_SAIDA / "populacao_municipios.csv"
_DIST_CACHE        = PASTA_SAIDA / "distribuidoras_municipios.csv"
_GEOJSON_EST_URL   = (
    "https://raw.githubusercontent.com/codeforamerica/click_that_hood"
    "/master/public/data/brazil-states.geojson"
)
_MUNICIPIOS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros"
    "/main/csv/municipios.csv"
)
_POPULACAO_URL = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/4714"
    "/periodos/2022/variaveis/93?localidades=N6[all]"
)
_GEOJSON_MUN_URL_BASE = (
    "https://servicodados.ibge.gov.br/api/v2/malhas"
    "/{uf_code}?resolucao=5&formato=application/vnd.geo%2Bjson"
)
_UF_PARA_IBGE: dict[str, str] = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}

# ─── IDENTIDADE VISUAL ────────────────────────────────────────────────────────

# Logo opcional — coloque o arquivo em assets/logo.png ao lado do script
_LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

_COLORSCALE_GRUGEEN: list[list] = [
    [0.00, "#E2E2E2"],
    [0.25, "#96D6B0"],
    [0.50, "#44AA6D"],
    [0.75, "#1D683C"],
    [1.00, "#013D1A"],
]
_COLORSCALE_OPORT: list[list] = [
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

# Demanda média estimada por divisão CNAE (kW/estabelecimento)
_DEMANDA_kW: dict[str, int] = {
    "05": 850,  "06": 2000, "07": 1500, "08": 800,  "09": 300,
    "10": 600,  "11": 500,  "12": 800,  "13": 700,  "14": 300,
    "15": 400,  "16": 500,  "17": 1200, "18": 400,  "19": 2000,
    "20": 1500, "21": 1000, "22": 800,  "23": 1200, "24": 3000,
    "25": 600,  "26": 500,  "27": 700,  "28": 800,  "29": 1500,
    "30": 1000, "31": 400,  "32": 350,  "33": 400,
    "35": 5000, "36": 1500, "37": 800,  "38": 600,  "39": 400,
    "41": 300,  "42": 500,  "43": 200,
    "46": 400,  "47": 300,
    "49": 250,  "50": 500,  "51": 2000, "52": 600,
    "55": 300,
    "61": 1000, "62": 400,  "63": 1500,
    "85": 250,  "86": 600,  "93": 400,
}


def _logo_data_uri() -> str:
    try:
        data = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        return ""


# ─── LOGGING ──────────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    PASTA_SAIDA.mkdir(exist_ok=True)
    pasta_logs = _AQUI / "logs"
    pasta_logs.mkdir(exist_ok=True)
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = "%(asctime)s | %(levelname)s | %(message)s"
    stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO, format=fmt,
        handlers=[
            logging.FileHandler(pasta_logs / f"mapa_prospecao_{ts}.log", encoding="utf-8"),
            logging.StreamHandler(stream),
        ],
    )
    return logging.getLogger(__name__)


# ─── DOWNLOAD ─────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 30) -> bytes:
    import gzip as gz
    req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return gz.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def _baixar_recurso(url: str, destino: Path, logger: logging.Logger) -> None:
    if destino.exists():
        logger.info("Cache: %s", destino.name)
        return
    logger.info("Baixando %s ...", destino.name)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(_fetch(url))
    logger.info("  %.1f KB", destino.stat().st_size / 1024)


# ─── NORMALIZAÇÃO ────────────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()
    # Unifica variantes de apóstrofo (curly quotes, modifier letter, etc.) → '
    for apos in ("‘", "’", "ʼ", "´", "`"):
        s = s.replace(apos, "'")
    return re.sub(r" {2,}", " ", s)


# Aliases: nome RF (após _normalizar) → nome IBGE (após _normalizar)
_ALIASES: dict[tuple[str, str], str] = {
    # CE
    ("SAO LUIZ DO CURU", "CE"):           "SAO LUIS DO CURU",
    # MA
    ("PINDARE MIRIM", "MA"):              "PINDARE-MIRIM",
    # MG
    ("AMPARO DA SERRA", "MG"):            "AMPARO DO SERRA",
    ("BARAO DO MONTE ALTO", "MG"):        "BARAO DE MONTE ALTO",
    ("BRASOPOLIS", "MG"):                 "BRAZOPOLIS",
    ("DONA EUZEBIA", "MG"):              "DONA EUSEBIA",
    ("OLHOS-D'AGUA", "MG"):              "OLHOS D'AGUA",
    ("PASSA VINTE", "MG"):               "PASSA-VINTE",
    ("PINGO D'AGUA", "MG"):              "PINGO-D'AGUA",
    ("SAO TOME DAS LETRAS", "MG"):        "SAO THOME DAS LETRAS",
    # PA
    ("ELDORADO DOS CARAJAS", "PA"):       "ELDORADO DO CARAJAS",
    ("SANTA ISABEL DO PARA", "PA"):       "SANTA IZABEL DO PARA",
    # PE
    ("ITAMARACA", "PE"):                  "ILHA DE ITAMARACA",
    ("LAGOA DO ITAENGA", "PE"):           "LAGOA DE ITAENGA",
    ("SAO CAITANO", "PE"):               "SAO CAETANO",
    # RJ
    ("PARATI", "RJ"):                     "PARATY",
    ("TRAJANO DE MORAIS", "RJ"):          "TRAJANO DE MORAES",
    # RN
    ("ASSU", "RN"):                       "ACU",
    ("BOA SAUDE", "RN"):                  "JANUARIO CICCO (BOA SAUDE)",
    ("CAMPO GRANDE", "RN"):              "AUGUSTO SEVERO (CAMPO GRANDE)",
    ("OLHO D'AGUA DO BORGES", "RN"):     "OLHO-D'AGUA DO BORGES",
    # RS
    ("ENTRE IJUIS", "RS"):               "ENTRE-IJUIS",
    ("SANTANA DO LIVRAMENTO", "RS"):      "SANT'ANA DO LIVRAMENTO",
    # SC
    ("BALNEARIO DE PICARRAS", "SC"):      "BALNEARIO PICARRAS",
    # SE
    ("GRACCHO CARDOSO", "SE"):            "GRACHO CARDOSO",
    # SP
    ("EMBU", "SP"):                       "EMBU DAS ARTES",
    ("FLORINEA", "SP"):                   "FLORINIA",
    ("MOJI-MIRIM", "SP"):                "MOGI MIRIM",
    # TO
    ("COUTO DE MAGALHAES", "TO"):         "COUTO MAGALHAES",
    ("SAO VALERIO DA NATIVIDADE", "TO"):  "SAO VALERIO",
}


# ─── CARREGAR E AGREGAR DADOS CNPJ ───────────────────────────────────────────

def _carregar_resumo(logger: logging.Logger) -> pd.DataFrame:
    logger.info("Carregando %s ...", ARQUIVO_RESUMO.name)
    df = pd.read_csv(ARQUIVO_RESUMO, sep=";", dtype=str, encoding="utf-8-sig")
    df["total_empresas"] = pd.to_numeric(df["total_empresas"], errors="coerce").fillna(0)
    df["matrizes"]       = pd.to_numeric(df["matrizes"],       errors="coerce").fillna(0)
    df["cnae_tier"]      = pd.to_numeric(df["cnae_tier"],      errors="coerce").fillna(3)
    df["demanda_kW"]     = df["cnae_divisao"].map(_DEMANDA_kW).fillna(300) * df["total_empresas"]
    logger.info("  %d linhas (combinações município × CNAE)", len(df))
    return df


def _agregar_por_municipio(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Agrega todas as divisões CNAE por município."""
    logger.info("Agregando por município ...")
    agg = (
        df.groupby(["uf", "nome_municipio"])
        .agg(
            total_empresas=("total_empresas", "sum"),
            tier1=("total_empresas", lambda x: x[df.loc[x.index, "cnae_tier"] == 1].sum()),
            tier2=("total_empresas", lambda x: x[df.loc[x.index, "cnae_tier"] == 2].sum()),
            demanda_MW=("demanda_kW", lambda x: x.sum() / 1000),
            cnae_top=("cnae_descricao", lambda x: (
                df.loc[x.index].groupby("cnae_descricao")["total_empresas"].sum().idxmax()
            )),
        )
        .reset_index()
    )
    agg["nome_norm"] = agg["nome_municipio"].apply(_normalizar)
    agg["nome_norm"] = agg.apply(
        lambda r: _ALIASES.get((r["nome_norm"], r["uf"]), r["nome_norm"]), axis=1
    )
    agg["regiao"] = agg["uf"].map(_UF_PARA_REGIAO).fillna("")
    logger.info("  %d municípios únicos", len(agg))
    return agg


# ─── GEOCODIFICAÇÃO ───────────────────────────────────────────────────────────

def _carregar_municipios_ibge(logger: logging.Logger) -> pd.DataFrame:
    _baixar_recurso(_MUNICIPIOS_URL, _MUNICIPIOS_CACHE, logger)
    df = pd.read_csv(_MUNICIPIOS_CACHE, encoding="utf-8", dtype=str)
    df["nome_norm"]  = df["nome"].apply(_normalizar)
    _ibge_uf = {v: k for k, v in _UF_PARA_IBGE.items()}
    df["uf_norm"]    = df["codigo_uf"].map(_ibge_uf)
    df["latitude"]   = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"]  = pd.to_numeric(df["longitude"], errors="coerce")
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.zfill(7)
    logger.info("Municípios IBGE: %d", len(df))
    return df


def _geocodificar(df_mun: pd.DataFrame, df_ibge: pd.DataFrame,
                  logger: logging.Logger) -> pd.DataFrame:
    lookup = df_ibge[["nome_norm", "uf_norm", "latitude", "longitude", "codigo_ibge"]]
    df = df_mun.merge(lookup, left_on=["nome_norm", "uf"],
                      right_on=["nome_norm", "uf_norm"], how="left")
    enc = df["codigo_ibge"].notna().sum()
    logger.info("Geocodificação: %d/%d (%.0f%%)", enc, len(df), 100 * enc / len(df))
    sem = df[df["codigo_ibge"].isna()]["nome_municipio"].unique()
    if len(sem):
        logger.warning("Sem coords (%d): %s%s",
                       len(sem), ", ".join(sem[:8]), " ..." if len(sem) > 8 else "")
    return df.dropna(subset=["codigo_ibge"]).copy()


# ─── GEOJSON TODOS OS MUNICÍPIOS ─────────────────────────────────────────────

def _geojson_todos(logger: logging.Logger) -> Path:
    """
    Cria (se necessário) um GeoJSON com TODOS os municípios combinando
    br_municipios_filtrado.geojson + br_municipios_lacunas.geojson.
    Se os dois caches não existirem ainda, baixa do IBGE.
    """
    if _GEOJSON_ALL_CACHE.exists():
        logger.info("Cache: %s", _GEOJSON_ALL_CACHE.name)
        return _GEOJSON_ALL_CACHE

    if _GEOJSON_MUN_CACHE.exists() and _GEOJSON_LAC_CACHE.exists():
        logger.info("Combinando GeoJSONs existentes → %s ...", _GEOJSON_ALL_CACHE.name)
        with open(_GEOJSON_MUN_CACHE, encoding="utf-8") as f:
            gj1 = json.load(f)
        with open(_GEOJSON_LAC_CACHE, encoding="utf-8") as f:
            gj2 = json.load(f)
        features = gj1.get("features", []) + gj2.get("features", [])
        del gj1, gj2
        gj_all = {"type": "FeatureCollection", "features": features}
        with open(_GEOJSON_ALL_CACHE, "w", encoding="utf-8") as f:
            json.dump(gj_all, f, separators=(",", ":"))
        logger.info("  %d features combinadas (%.0f KB)",
                    len(features), _GEOJSON_ALL_CACHE.stat().st_size / 1024)
        del features, gj_all
        gc.collect()
        return _GEOJSON_ALL_CACHE

    # Fallback: baixar tudo do IBGE
    logger.info("Baixando GeoJSON de todos os municípios do IBGE (27 estados) ...")
    features: list = []
    for uf_nome, uf_code in sorted(_UF_PARA_IBGE.items()):
        url = _GEOJSON_MUN_URL_BASE.format(uf_code=uf_code)
        try:
            raw = _fetch(url, timeout=30)
            gj_uf = json.loads(raw.decode("utf-8"))
            for feat in gj_uf.get("features", []):
                codarea = str(feat.get("properties", {}).get("codarea", "")).zfill(7)
                feat["properties"]["codarea"] = codarea
                features.append(feat)
            logger.info("  %s: %d features", uf_nome, len(gj_uf.get("features", [])))
            del gj_uf, raw
        except Exception as exc:
            logger.warning("  %s: erro — %s", uf_nome, exc)

    gj_all = {"type": "FeatureCollection", "features": features}
    with open(_GEOJSON_ALL_CACHE, "w", encoding="utf-8") as f:
        json.dump(gj_all, f, separators=(",", ":"))
    logger.info("GeoJSON completo salvo (%.0f KB)", _GEOJSON_ALL_CACHE.stat().st_size / 1024)
    del features, gj_all
    gc.collect()
    return _GEOJSON_ALL_CACHE


# ─── POPULAÇÃO ────────────────────────────────────────────────────────────────

def _carregar_populacao(logger: logging.Logger) -> pd.DataFrame:
    if _POPULACAO_CACHE.exists():
        logger.info("Cache: %s", _POPULACAO_CACHE.name)
        df = pd.read_csv(_POPULACAO_CACHE, dtype=str)
        df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
        return df
    logger.info("Baixando Censo 2022 ...")
    raw  = _fetch(_POPULACAO_URL, timeout=30)
    data = json.loads(raw.decode("utf-8"))
    rows = [
        {"codigo_ibge": s["localidade"]["id"].strip().zfill(7),
         "populacao": s["serie"].get("2022", "")}
        for s in data[0]["resultados"][0]["series"]
    ]
    df = pd.DataFrame(rows)
    df.to_csv(_POPULACAO_CACHE, index=False, encoding="utf-8")
    df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
    logger.info("Censo 2022: %d municípios", len(df))
    return df


# ─── FORMATAÇÃO ───────────────────────────────────────────────────────────────

def _br(v: float, d: int = 0) -> str:
    fmt = f"{v:,.{d}f}"
    return fmt.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_int(v: float)   -> str: return _br(int(v))
def _fmt_mw(v: float)    -> str: return _br(v, 1) + " MW"
def _fmt_dens(v: float)  -> str: return _br(v, 1) + " emp/1k hab"
def _fmt_pop(v: float)   -> str: return _br(int(v)) + " hab"


# ─── MAPAS ────────────────────────────────────────────────────────────────────

def _geo_layout() -> dict:
    return dict(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")


def _fig_layout() -> dict:
    return dict(
        coloraxis_colorbar=dict(
            thickness=15, len=0.75,
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#E2E2E2", borderwidth=1,
        ),
        margin={"r": 10, "t": 60, "l": 10, "b": 10},
        paper_bgcolor="#FFFFFF",
        font=dict(family='"General Sans", Calibri, Arial, sans-serif',
                  size=12, color="#1C1C1C"),
        height=640,
        title_font=dict(family='"Epilogue", Arial, Helvetica, sans-serif',
                        size=14, color="#013D1A"),
    )


def _mapa_coro(
    df: pd.DataFrame,
    geojson_path: Path,
    coluna: str,
    titulo: str,
    label_cb: str,
    fmt_hover: Callable,
    logger: logging.Logger,
    colorscale=_COLORSCALE_GRUGEEN,
    use_log: bool = True,
    hover_extra: list[tuple[str, str, Callable]] | None = None,
    df_sem_dado: pd.DataFrame | None = None,
) -> str:
    logger.info("  Carregando GeoJSON (%s) ...", geojson_path.name)
    with open(geojson_path, encoding="utf-8") as f:
        geojson = json.load(f)

    df = df[df[coluna].notna() & (df[coluna] > 0)].copy()
    df["_label"] = df["nome_municipio"].str.title() + " — " + df["uf"]

    coluna_plot = coluna
    range_cor   = None
    if use_log:
        coluna_plot = f"__log_{coluna}"
        df[coluna_plot] = np.log1p(df[coluna])
        range_cor = (0.0, float(df[coluna_plot].max()))

    hover = (
        "<b>" + df["_label"] + "</b><br>"
        + label_cb + ": " + df[coluna].apply(fmt_hover)
    )
    if hover_extra:
        for col_ex, lbl_ex, fmt_ex in hover_extra:
            if col_ex in df.columns:
                hover = hover + "<br>" + lbl_ex + ": " + df[col_ex].apply(fmt_ex)
    if "populacao" in df.columns:
        hover = hover + "<br>Habitantes: " + df["populacao"].apply(
            lambda x: _br(int(x)) + " hab" if pd.notna(x) and x > 0 else "n/d"
        )
    df["hover"] = hover

    logger.info("  Renderizando '%s' (%d municípios) ...", titulo, len(df))
    fig = px.choropleth(
        df, geojson=geojson, locations="codigo_ibge",
        featureidkey="properties.codarea",
        color=coluna_plot, color_continuous_scale=colorscale,
        hover_name="_label", custom_data=["hover"],
        labels={coluna_plot: label_cb},
        title=titulo.upper(),
        range_color=range_cor,
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="rgba(255,255,255,0.4)",
        marker_line_width=0.3,
    )
    fig.update_geos(**_geo_layout())
    fig.update_layout(**_fig_layout())

    if use_log:
        log_max   = float(df[coluna_plot].max())
        tick_vals = [i * log_max / 5 for i in range(6)]
        tick_txt  = [fmt_hover(float(np.expm1(v))) for v in tick_vals]
        fig.update_layout(coloraxis_colorbar=dict(
            thickness=15, len=0.75,
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#E2E2E2", borderwidth=1,
            tickvals=tick_vals, ticktext=tick_txt,
            title=f"{label_cb}<br><sup>escala log</sup>",
        ))
    else:
        fig.update_layout(coloraxis_colorbar_title=label_cb)

    # Municípios sem dado: sempre pintar de cinza para não deixar brancos
    codigos_plot = set(df["codigo_ibge"].dropna().astype(str))
    codigos_geojson = {
        str(feat.get("properties", {}).get("codarea", ""))
        for feat in geojson.get("features", [])
    }
    codigos_cinza = list(codigos_geojson - codigos_plot)
    if codigos_cinza:
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=codigos_cinza,
            z=[0] * len(codigos_cinza),
            featureidkey="properties.codarea",
            colorscale=[[0, "#CECECE"], [1, "#CECECE"]],
            text=["Sem dados"] * len(codigos_cinza),
            hovertemplate="%{text}<extra></extra>",
            marker_line_color="rgba(255,255,255,0.4)",
            marker_line_width=0.3,
            showscale=False, showlegend=False,
        ))
        logger.info("  %d municípios sem dado cobertos (cinza)", len(codigos_cinza))

    logger.info("  Serializando ...")
    html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    del fig, geojson
    gc.collect()
    logger.info("  OK (%.1f MB)", len(html) / 1024 ** 2)
    return html


def _mapa_oportunidades(
    df: pd.DataFrame,
    geojson_path: Path,
    logger: logging.Logger,
) -> str:
    """
    Mapa de oportunidades: municípios com potencial industrial mas sem ACL.
    Usa br_municipios_lacunas.geojson (municípios sem consumidores ACL no CCEE).
    Colore pelo número de empresas Tier 1.
    """
    logger.info("  Carregando GeoJSON lacunas (%s) ...", _GEOJSON_LAC_CACHE.name)
    if not _GEOJSON_LAC_CACHE.exists():
        logger.warning("GeoJSON de lacunas não encontrado. Aba de oportunidades indisponível.")
        return "<p style='padding:20px'>Execute mapa_consumo_mensal.py para gerar o cache de lacunas.</p>"

    with open(_GEOJSON_LAC_CACHE, encoding="utf-8") as f:
        geojson_lac = json.load(f)

    # Municípios sem ACL = apenas os que estão no geojson de lacunas
    codigos_sem_acl = {
        str(feat.get("properties", {}).get("codarea", "")).zfill(7)
        for feat in geojson_lac.get("features", [])
    }

    # Municípios com CNPJ industrial que NÃO têm ACL
    df_oport = df[df["codigo_ibge"].isin(codigos_sem_acl) & (df["tier1"] > 0)].copy()
    df_oport = df_oport.sort_values("tier1", ascending=False)
    logger.info("  Oportunidades: %d municípios sem ACL com empresas Tier 1", len(df_oport))

    if len(df_oport) == 0:
        return "<p style='padding:20px'>Nenhum município de oportunidade encontrado.</p>"

    df_oport["_label"] = df_oport["nome_municipio"].str.title() + " — " + df_oport["uf"]
    df_oport["__log"] = np.log1p(df_oport["tier1"])
    log_max = float(df_oport["__log"].max())

    hover = (
        "<b>" + df_oport["_label"] + "</b><br>"
        + "Empresas industriais (Tier 1): " + df_oport["tier1"].apply(_fmt_int) + "<br>"
        + "Total de empresas: " + df_oport["total_empresas"].apply(_fmt_int) + "<br>"
        + "Demanda estimada: " + df_oport["demanda_MW"].apply(_fmt_mw) + "<br>"
        + "<i>Sem consumidores no ACL</i>"
    )
    if "populacao" in df_oport.columns:
        hover = hover + "<br>Habitantes: " + df_oport["populacao"].apply(
            lambda x: _br(int(x)) + " hab" if pd.notna(x) and x > 0 else "n/d"
        )
    df_oport["hover"] = hover

    logger.info("  Renderizando mapa de oportunidades ...")
    fig = px.choropleth(
        df_oport, geojson=geojson_lac, locations="codigo_ibge",
        featureidkey="properties.codarea",
        color="__log", color_continuous_scale=_COLORSCALE_OPORT,
        hover_name="_label", custom_data=["hover"],
        title="OPORTUNIDADES — MUNICÍPIOS SEM ACL COM CONCENTRAÇÃO INDUSTRIAL",
        range_color=(0.0, log_max),
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker_line_color="rgba(255,255,255,0.4)", marker_line_width=0.3,
    )
    fig.update_geos(**_geo_layout())
    fig.update_layout(**_fig_layout())

    # Colorbar com escala real
    tick_vals = [i * log_max / 5 for i in range(6)]
    tick_txt  = [_fmt_int(float(np.expm1(v))) for v in tick_vals]
    fig.update_layout(coloraxis_colorbar=dict(
        thickness=15, len=0.75,
        bgcolor="rgba(255,255,255,0.92)",
        bordercolor="#E2E2E2", borderwidth=1,
        tickvals=tick_vals, ticktext=tick_txt,
        title="Tier 1<br><sup>escala log</sup>",
    ))

    # Sobreposição: municípios COM ACL em cinza
    with open(_GEOJSON_MUN_CACHE, encoding="utf-8") as f:
        geojson_acl = json.load(f)
    fig.add_trace(go.Choropleth(
        geojson=geojson_acl,
        locations=[feat.get("properties", {}).get("codarea", "")
                   for feat in geojson_acl.get("features", [])],
        z=[0] * len(geojson_acl.get("features", [])),
        featureidkey="properties.codarea",
        colorscale=[[0, "#CECECE"], [1, "#CECECE"]],
        text=["Município com consumidores ACL"] * len(geojson_acl.get("features", [])),
        hovertemplate="%{text}<extra></extra>",
        marker_line_color="rgba(255,255,255,0.4)", marker_line_width=0.3,
        showscale=False, showlegend=False,
    ))

    html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
    del fig, geojson_lac, geojson_acl
    gc.collect()
    logger.info("  OK (%.1f MB)", len(html) / 1024 ** 2)
    return html


# ─── TABELA ───────────────────────────────────────────────────────────────────

def _tabela_html(
    df: pd.DataFrame,
    colunas: list[tuple[str, str, Callable | None]],
    ibge_col: str = "codigo_ibge",
) -> str:
    thead = "<tr>" + "".join(
        f'<th onclick="sortTable(this)" data-col="{i}">'
        f'{h} <span class="sort-arrow">&#x21C5;</span></th>'
        for i, (_, h, _) in enumerate(colunas)
    ) + "</tr>"
    rows = []
    for _, row in df.iterrows():
        ibge = str(row.get(ibge_col, "")).zfill(7) if ibge_col in df.columns else ""
        cells = []
        for col, _, fmt in colunas:
            val = row.get(col)
            if fmt is not None and pd.notna(val):
                cells.append(f'<td data-value="{val}">{fmt(val)}</td>')
            else:
                cells.append(f'<td>{val if pd.notna(val) else ""}</td>')
        rows.append(f'<tr data-ibge="{ibge}">' + "".join(cells) + "</tr>")
    total = len(rows)
    return (
        '<div class="table-controls">'
        '<input type="text" class="table-filter" placeholder="Filtrar..." oninput="filterTable(this)">'
        f'<span class="table-count">{total} linhas</span>'
        '</div>'
        '<div class="table-wrapper">'
        f'<table class="data-table"><thead>{thead}</thead><tbody>{"".join(rows)}</tbody></table>'
        '</div>'
    )


# ─── DADOS DE FILTRO ─────────────────────────────────────────────────────────

def _carregar_distribuidoras(logger: logging.Logger) -> dict[str, str]:
    """Carrega mapeamento IBGE → distribuidora gerado por mapa_consumo_mensal.py."""
    if not _DIST_CACHE.exists():
        logger.info("Cache distribuidoras não encontrado (execute mapa_consumo_mensal.py para gerar)")
        return {}
    try:
        df = pd.read_csv(_DIST_CACHE, dtype=str, encoding="utf-8")
        df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.zfill(7)
        mapping = dict(zip(df["codigo_ibge"], df["distribuidora"].fillna("").str.upper()))
        logger.info("Distribuidoras: %d municípios carregados", len(mapping))
        return mapping
    except Exception as exc:
        logger.warning("Erro ao carregar distribuidoras: %s", exc)
        return {}


def _preparar_filtro_dados(
    df_raw: pd.DataFrame,
    df_geo: pd.DataFrame,
    geojson_todos_path: Path,
    lac_codes: set[str],
    logger: logging.Logger,
) -> dict:
    """Serializa dados compactos para filtros JavaScript (Região, UF, CNAE)."""
    logger.info("Preparando dados de filtro ...")

    # CNAE lookup list
    cnae_df = (
        df_raw[["cnae_divisao", "cnae_descricao", "cnae_tier"]]
        .drop_duplicates()
        .sort_values("cnae_divisao")
    )
    cnaes_list = [
        [str(r["cnae_divisao"]), str(r["cnae_descricao"]), int(float(r["cnae_tier"]))]
        for _, r in cnae_df.iterrows()
    ]
    cnae_idx_map = {c[0]: i for i, c in enumerate(cnaes_list)}

    # All GeoJSON codes
    logger.info("  Lendo códigos IBGE do GeoJSON ...")
    with open(geojson_todos_path, encoding="utf-8") as f:
        gj = json.load(f)
    all_codes = [
        str(feat.get("properties", {}).get("codarea", "")).zfill(7)
        for feat in gj.get("features", [])
    ]
    all_codes = [c for c in all_codes if c and c != "0000000"]
    del gj
    gc.collect()

    # Distribuidoras por IBGE (cache externo, gerado por mapa_consumo_mensal.py)
    dist_map = _carregar_distribuidoras(logger)
    dists_list = sorted({v for v in dist_map.values() if v})

    def _val(row: pd.Series, col: str, default: float = 0.0) -> float:
        v = row.get(col)
        return float(v) if pd.notna(v) else default

    # Build per-tab municipality data
    tabs: dict[str, dict] = {}
    for tab_id, (val_col, extra_keys) in [
        ("tier1",   ("tier1",          ["total_empresas", "demanda_MW", "populacao", "cnae_top"])),
        ("total",   ("total_empresas", ["tier1", "tier2", "demanda_MW", "cnae_top"])),
        ("demanda", ("demanda_MW",     ["tier1", "total_empresas", "cnae_top"])),
        ("dens",    ("tier1_por_1k_hab", ["tier1", "populacao"])),
    ]:
        mun_data: dict[str, dict] = {}
        for _, row in df_geo.iterrows():
            ibge = str(row.get("codigo_ibge", "")).zfill(7)
            if not ibge or ibge == "0000000":
                continue
            v = _val(row, val_col)
            if v <= 0:
                continue
            d: dict = {
                "uf":   str(row.get("uf", "")),
                "reg":  str(row.get("regiao", "")),
                "dist": dist_map.get(ibge, ""),
                "v":    round(v, 4),
                "lv":   round(float(np.log1p(v)), 6),
                "nome": str(row.get("nome_municipio", "")).title(),
            }
            for k in extra_keys:
                if k == "cnae_top":
                    d["cnaeTop"] = str(row.get("cnae_top", ""))[:60]
                    continue
                ev = _val(row, k)
                if k == "populacao":
                    d["pop"] = int(ev) if ev > 0 else 0
                elif k in ("tier1", "tier2", "total_empresas"):
                    d[k.replace("_empresas", "")] = round(ev, 0)
                elif k == "demanda_MW":
                    d["dmw"] = round(ev, 2)
            mun_data[ibge] = d
        log_max = float(np.log1p(max((d["v"] for d in mun_data.values()), default=1)))
        tabs[tab_id] = {"munData": mun_data, "logMax": round(log_max, 6)}

    # oport shares tier1 data but restricted to lac_codes in JS
    tabs["oport"] = {"munData": tabs["tier1"]["munData"], "logMax": tabs["tier1"]["logMax"]}

    # Raw CNAE data: {ibge: [[cnae_idx, tier, count, demanda_kW], ...]}
    logger.info("  Preparando dados CNAE brutos por município ...")
    df_raw = df_raw.copy()
    df_raw["_n"]  = pd.to_numeric(df_raw["total_empresas"], errors="coerce").fillna(0)
    df_raw["_t"]  = pd.to_numeric(df_raw["cnae_tier"],      errors="coerce").fillna(3)
    df_raw["_dkw"] = df_raw["cnae_divisao"].map(_DEMANDA_kW).fillna(300) * df_raw["_n"]

    ibge_lkp = (
        df_geo[["uf", "nome_municipio", "codigo_ibge"]]
        .assign(codigo_ibge=lambda x: x["codigo_ibge"].astype(str).str.zfill(7))
    )
    df_m = df_raw.merge(ibge_lkp, on=["uf", "nome_municipio"], how="inner")

    cnae_data: dict[str, list] = {}
    for ibge, grp in df_m.groupby("codigo_ibge"):
        ibge_s = str(ibge).zfill(7)
        entries = []
        for _, r in grp.iterrows():
            cidx = cnae_idx_map.get(str(r["cnae_divisao"]), -1)
            if cidx < 0:
                continue
            cnt = int(r["_n"])
            if cnt <= 0:
                continue
            entries.append([cidx, int(r["_t"]), cnt, int(r["_dkw"])])
        if entries:
            cnae_data[ibge_s] = entries

    logger.info("  CNAE raw: %d municípios", len(cnae_data))

    return {
        "reg":      _UF_REGIAO,
        "ufs":      sorted(_UF_PARA_IBGE.keys()),
        "cnaes":    cnaes_list,
        "cnaeIdx":  [c[0] for c in cnaes_list],
        "allCodes": all_codes,
        "lacCodes": sorted(lac_codes),
        "dists":    dists_list,
        "tabs":     tabs,
        "cnaeData": cnae_data,
    }


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

def _salvar_dashboard(
    figs: dict[str, tuple[str, str, str]],
    logger: logging.Logger,
    filtro_dados: dict | None = None,
) -> Path:
    logo_uri = _logo_data_uri()
    logo_tag = (
        f'<img src="{logo_uri}" alt="Grugeen" class="header-logo">'
        if logo_uri else '<span class="header-brand-text">GRUGEEN</span>'
    )
    tabs_html = ""
    panels_html = ""
    for i, (tid, (html_fig, html_tbl, label)) in enumerate(figs.items()):
        active = "active" if i == 0 else ""
        tabs_html += (
            f'<button class="tab-btn {active}" onclick="showTab(\'{tid}\',this)">'
            f'{label}</button>\n'
        )
        panels_html += (
            f'<div id="tab-{tid}" class="tab-panel {active}">\n'
            f'  <div class="view-controls">\n'
            f'    <button class="view-btn active" onclick="toggleView(\'{tid}\',\'map\',this)">&#128506; Mapa</button>\n'
            f'    <button class="view-btn" onclick="toggleView(\'{tid}\',\'table\',this)">&#128203; Tabela</button>\n'
            f'  </div>\n'
            f'  <div class="view-map">{html_fig}</div>\n'
            f'  <div class="view-table">{html_tbl}</div>\n'
            f'</div>\n'
        )

    # Serialize filter data (NaN → null)
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
    cnae_sel_html = ""
    dist_sel_html = ""
    if filtro_dados is not None:
        fd_json = json.dumps(_clean_fd(filtro_dados), ensure_ascii=False, separators=(",", ":"))
        cnae_sel_html = (
            '<select class="filter-sel" id="fil-cnae" onchange="applyFilters()" title="Filtrar por divisão CNAE">'
            '<option value="">Todos os setores (CNAE)</option>'
            '</select>'
        )
        if filtro_dados.get("dists"):
            opts = "".join(
                f'<option value="{d}">{d}</option>' for d in filtro_dados["dists"]
            )
            dist_sel_html = (
                '<select class="filter-sel" id="fil-dist" onchange="applyFilters()" '
                'title="Filtrar por concessionária distribuidora">'
                f'<option value="">Todas as distribuidoras</option>{opts}</select>'
            )

    template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prospecção CNPJs — Potencial Mercado Livre | Grugeen</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Epilogue:wght@600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --verde:#1D683C;--verde-escuro:#013D1A;--grafite:#1C1C1C;
      --offwhite:#E2E2E2;--cinza:#A6A6A6;--laranja:#EC6C41;
      --font-heading:"Epilogue",Arial,Helvetica,sans-serif;
      --font-body:"General Sans",Calibri,Arial,sans-serif;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    html,body{{height:100%}}
    body{{font-family:var(--font-body);background:var(--offwhite);color:var(--grafite);display:flex;flex-direction:column;min-height:100vh}}
    header{{background:var(--verde-escuro);border-bottom:3px solid var(--verde);padding:12px 28px;flex-shrink:0;display:flex;align-items:center;gap:20px}}
    .header-logo{{height:36px;width:auto;flex-shrink:0}}
    .header-brand-text{{font-family:var(--font-heading);font-weight:700;font-size:1.2rem;text-transform:uppercase;letter-spacing:.1em;color:var(--offwhite);flex-shrink:0}}
    .header-divider{{width:1px;height:30px;background:rgba(226,226,226,.25);flex-shrink:0}}
    .header-info{{flex:1}}
    .header-info h1{{font-family:var(--font-heading);font-weight:600;font-size:.95rem;text-transform:uppercase;letter-spacing:.05em;color:var(--offwhite)}}
    .header-info p{{font-family:var(--font-body);font-size:.75rem;color:var(--cinza);margin-top:3px}}
    .note{{padding:5px 28px;font-size:.72rem;color:var(--grafite);background:#fff;border-bottom:1px solid var(--offwhite);flex-shrink:0}}
    /* ── Filtros ─── */
    .filter-bar{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 20px;background:#eef3ef;border-bottom:2px solid var(--offwhite);flex-shrink:0}}
    .filter-label{{font-family:var(--font-heading);font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--verde-escuro);white-space:nowrap}}
    .filter-sel{{padding:5px 10px;border:1px solid #bfcfc3;border-radius:4px;font-family:var(--font-body);font-size:.8rem;color:var(--grafite);background:#fff;outline:none;cursor:pointer;max-width:240px;min-width:140px}}
    .filter-sel:focus{{border-color:var(--verde);box-shadow:0 0 0 2px rgba(29,104,60,.12)}}
    .filter-clear{{padding:5px 12px;border:1px solid #bfcfc3;border-radius:4px;font-family:var(--font-body);font-size:.78rem;font-weight:600;background:#fff;color:var(--grafite);cursor:pointer;transition:background .15s}}
    .filter-clear:hover{{background:var(--offwhite)}}
    .filter-count{{font-size:.75rem;color:var(--cinza);margin-left:4px;white-space:nowrap}}
    /* ── Abas ─── */
    .tabs{{display:flex;flex-wrap:wrap;gap:2px;padding:10px 20px 0;background:var(--offwhite);flex-shrink:0}}
    .tab-btn{{padding:7px 20px;border:none;border-radius:6px 6px 0 0;cursor:pointer;font-family:var(--font-body);font-size:.82rem;font-weight:600;background:#c4d1c6;color:var(--grafite);transition:background .15s,color .15s}}
    .tab-btn.active{{background:#fff;color:var(--verde-escuro);border-top:2px solid var(--verde)}}
    .tab-btn:hover:not(.active){{background:#b4c5b8}}
    .tab-panel{{display:none;flex:1;background:#fff}}
    .tab-panel.active{{display:flex;flex-direction:column}}
    .view-controls{{display:flex;gap:6px;padding:6px 10px;background:#f4f7f4;border-bottom:1px solid var(--offwhite);flex-shrink:0}}
    .view-btn{{padding:4px 14px;border:1px solid var(--cinza);border-radius:4px;cursor:pointer;font-family:var(--font-body);font-size:.78rem;font-weight:600;background:#fff;color:var(--grafite);transition:background .15s,color .15s}}
    .view-btn.active{{background:var(--verde);color:#fff;border-color:var(--verde)}}
    .view-btn:hover:not(.active){{background:var(--offwhite)}}
    .view-map{{flex:1;padding:4px 8px 8px}}
    .view-map>div{{flex:1!important;min-height:640px}}
    .view-table{{display:none;flex-direction:column;padding:14px 16px;overflow:hidden}}
    .table-controls{{display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-shrink:0}}
    .table-filter{{padding:6px 12px;border:1px solid var(--cinza);border-radius:4px;font-family:var(--font-body);font-size:.85rem;width:300px;outline:none}}
    .table-filter:focus{{border-color:var(--verde);box-shadow:0 0 0 2px rgba(29,104,60,.15)}}
    .table-count{{font-size:.78rem;color:var(--cinza)}}
    .table-wrapper{{overflow:auto;max-height:620px;border:1px solid var(--offwhite);border-radius:4px}}
    .data-table{{width:100%;border-collapse:collapse;font-family:var(--font-body);font-size:.82rem}}
    .data-table thead th{{background:var(--verde);color:#fff;padding:9px 14px;text-align:left;font-family:var(--font-heading);font-size:.74rem;text-transform:uppercase;letter-spacing:.04em;cursor:pointer;white-space:nowrap;user-select:none;position:sticky;top:0;z-index:1}}
    .data-table thead th:hover{{background:var(--verde-escuro)}}
    .data-table tbody tr:nth-child(even){{background:#f6fbf8}}
    .data-table tbody tr:hover{{background:#dff0e7}}
    .data-table td{{padding:7px 14px;border-bottom:1px solid var(--offwhite);white-space:nowrap}}
    .sort-arrow{{opacity:.55;margin-left:5px;font-size:.85em}}
    footer{{background:var(--verde-escuro);color:var(--cinza);font-family:var(--font-body);font-size:.68rem;text-align:center;padding:6px;flex-shrink:0}}
  </style>
</head>
<body>
  <header>
    {logo_tag}
    <div class="header-divider"></div>
    <div class="header-info">
      <h1>Prospecção de Mercado Livre — Concentração Industrial por Município</h1>
      <p>Fonte: CNPJ Dados Abertos — Receita Federal (jun/2026) &nbsp;·&nbsp; 15,1 milhões de empresas ativas em setores de alto consumo &nbsp;·&nbsp; Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </div>
  </header>
  <div class="note">
    Tier 1 = Indústria extrativa, transformação, eletricidade/gás, telecomunicações, data centers &nbsp;·&nbsp;
    Demanda estimada com benchmarks setoriais EPE/ANEEL (orientativa, não medida) &nbsp;·&nbsp;
    Oportunidades = municípios com empresas industriais e sem consumidores no ACL
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
    {cnae_sel_html}
    <button class="filter-clear" onclick="clearFilters()" title="Remover todos os filtros">&#10005; Limpar</button>
    <span class="filter-count" id="filter-count"></span>
  </div>
  <div class="tabs">{tabs_html}</div>
  {panels_html}
  <footer>Grugeen Consultoria Ltda &nbsp;·&nbsp; Dados: CNPJ RF / IBGE &nbsp;·&nbsp; {datetime.now().year}</footer>
  <script>window._FD={fd_json};</script>
  <script>
    /* ── Inicialização dos dropdowns ─── */
    (function(){{
      var fd=window._FD;
      if(!fd)return;
      var uSel=document.getElementById('fil-uf');
      fd.ufs.forEach(function(u){{uSel.add(new Option(u,u))}});
      var cSel=document.getElementById('fil-cnae');
      if(cSel){{
        var tLbl={{1:'Tier 1',2:'Tier 2',3:'Tier 3'}};
        fd.cnaes.forEach(function(c){{cSel.add(new Option('['+tLbl[c[2]]+'] '+c[1],c[0]))}});
      }}
    }})();

    /* ── Navegação entre abas ─── */
    function showTab(n,b){{
      document.querySelectorAll('.tab-panel').forEach(function(p){{p.classList.remove('active')}});
      document.querySelectorAll('.tab-btn').forEach(function(x){{x.classList.remove('active')}});
      var p=document.getElementById('tab-'+n);
      p.classList.add('active');b.classList.add('active');
      p.querySelectorAll('.plotly-graph-div').forEach(function(d){{if(d.layout)Plotly.relayout(d,{{autosize:true}})}});
      applyFilters();
    }}
    function toggleView(t,v,b){{
      var p=document.getElementById('tab-'+t);
      p.querySelector('.view-map').style.display=v==='map'?'block':'none';
      var tbl=p.querySelector('.view-table');tbl.style.display=v==='table'?'flex':'none';
      p.querySelectorAll('.view-btn').forEach(function(x){{x.classList.remove('active')}});b.classList.add('active');
      if(v==='map')p.querySelectorAll('.plotly-graph-div').forEach(function(d){{if(d.layout)Plotly.relayout(d,{{autosize:true}})}});
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

    /* ── Filtros ─── */
    function onRegiaoChange(){{
      var fd=window._FD;if(!fd)return;
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
      var cSel=document.getElementById('fil-cnae');if(cSel)cSel.value='';
      var dSel=document.getElementById('fil-dist');if(dSel)dSel.value='';
      onRegiaoChange();
    }}
    function applyFilters(){{
      var fd=window._FD;if(!fd)return;
      var regVal=document.getElementById('fil-regiao').value;
      var ufVal=document.getElementById('fil-uf').value;
      var cSel=document.getElementById('fil-cnae');
      var cnaeVal=cSel?cSel.value:'';
      var dSel=document.getElementById('fil-dist');
      var distVal=dSel?dSel.value:'';
      var activePanel=document.querySelector('.tab-panel.active');
      if(!activePanel)return;
      var tabId=activePanel.id.replace('tab-','');
      _applyToTab(tabId,regVal,ufVal,cnaeVal,distVal);
    }}

    /* ── Formatadores ─── */
    function _fN(v){{return Math.round(v||0).toLocaleString('pt-BR')}}
    function _fMW(v){{return (v||0).toLocaleString('pt-BR',{{minimumFractionDigits:1,maximumFractionDigits:1}})+' MW'}}
    function _fD(v){{return (v||0).toLocaleString('pt-BR',{{minimumFractionDigits:1,maximumFractionDigits:1}})+' emp/1k hab'}}
    function _fP(v){{return v>0?_fN(v)+' hab':'n/d'}}

    function _hover(d,tid,v){{
      var L='<b>'+d.nome+' — '+d.uf+'</b><br>';
      var P=(d.pop||0)>0?'<br>Habitantes: '+_fP(d.pop):'';
      var Di=d.dist?'<br>Distribuidora: '+d.dist:'';
      if(tid==='tier1'||tid==='oport')return L+'Empresas Tier 1: '+_fN(v)+'<br>Total de empresas: '+_fN(d.total||0)+'<br>Demanda estimada: '+_fMW(d.dmw||0)+P+Di;
      if(tid==='total')return L+'Total de empresas: '+_fN(v)+'<br>Tier 1: '+_fN(d.t1||0)+'<br>Demanda estimada: '+_fMW(d.dmw||0)+Di;
      if(tid==='demanda')return L+'Demanda estimada: '+_fMW(v)+'<br>Empresas Tier 1: '+_fN(d.t1||0)+'<br>Total: '+_fN(d.total||0)+Di;
      if(tid==='dens')return L+'Densidade: '+_fD(v)+'<br>Tier 1: '+_fN(d.t1||0)+P+Di;
      return L+String(v);
    }}

    function _applyToTab(tabId,regVal,ufVal,cnaeVal,distVal){{
      var fd=window._FD;if(!fd)return;
      var tabData=fd.tabs[tabId];if(!tabData||!tabData.munData)return;
      var filtUfs=ufVal?[ufVal]:(regVal?fd.reg[regVal]:null);
      var lacSet=tabId==='oport'?new Set(fd.lacCodes):null;
      var locs=[],zVals=[],hoverArr=[];
      var munData=tabData.munData;
      Object.keys(munData).forEach(function(ibge){{
        var d=munData[ibge];
        if(filtUfs&&filtUfs.indexOf(d.uf)===-1)return;
        if(lacSet&&!lacSet.has(ibge))return;
        if(distVal&&d.dist!==distVal)return;
        var v;
        if(cnaeVal){{
          var raw=fd.cnaeData?fd.cnaeData[ibge]:null;if(!raw)return;
          var cidx=fd.cnaeIdx.indexOf(cnaeVal);if(cidx<0)return;
          var entry=null;
          for(var i=0;i<raw.length;i++){{if(raw[i][0]===cidx){{entry=raw[i];break}}}}
          if(!entry||entry[2]<=0)return;
          if(tabId==='tier1'||tabId==='oport'){{if(entry[1]!==1)return;v=entry[2];}}
          else if(tabId==='total'){{v=entry[2];}}
          else if(tabId==='demanda'){{v=entry[3]/1000;}}
          else if(tabId==='dens'){{if(!(d.pop>0))return;v=entry[2]*1000/d.pop;}}
          else{{v=entry[2];}}
        }}else{{v=d.v;}}
        if(!(v>0))return;
        locs.push(ibge);zVals.push(Math.log1p(v));hoverArr.push([_hover(d,tabId,v)]);
      }});
      var filtSet=new Set(locs);
      var grayCodes=fd.allCodes.filter(function(c){{return!filtSet.has(c)}});
      var panel=document.getElementById('tab-'+tabId);if(!panel)return;
      var plotDiv=panel.querySelector('.plotly-graph-div');
      if(plotDiv&&plotDiv.data&&plotDiv.data.length>0){{
        Plotly.restyle(plotDiv,{{locations:[locs],z:[zVals],customdata:[hoverArr]}},[0]);
        var li=plotDiv.data.length-1;
        if(li>0)Plotly.restyle(plotDiv,{{locations:[grayCodes],z:[new Array(grayCodes.length).fill(0)]}},[li]);
        _zoomMap(plotDiv,regVal,ufVal);
      }}
      /* Filtrar tabela */
      var tvEl=panel.querySelector('.view-table');
      if(tvEl){{
        var rows=tvEl.querySelectorAll('.data-table tbody tr');
        var shown=0;
        rows.forEach(function(row){{
          var rowUf=row.cells[1]?row.cells[1].textContent.trim():'';
          var show=(!filtUfs||filtUfs.indexOf(rowUf)>-1);
          if(show&&(cnaeVal||distVal)){{var ri=row.dataset.ibge||'';show=!ri||filtSet.has(ri);}}
          row.style.display=show?'':'none';if(show)shown++;
        }});
        var cntEl=tvEl.querySelector('.table-count');
        if(cntEl)cntEl.textContent=shown+' de '+rows.length+' linhas';
      }}
      var fci=document.getElementById('filter-count');
      if(fci)fci.textContent=locs.length+' município'+(locs.length!==1?'s':'');
    }}

    /* ── Filtro de texto na tabela ─── */
    function filterTable(inp){{
      var f=inp.value.toLowerCase();
      var tv=inp.closest('.view-table');
      var rows=tv.querySelectorAll('.data-table tbody tr');
      var c=0;
      rows.forEach(function(r){{
        if(r.style.display==='none'&&f)return; /* respeita filtro de mapa */
        var s=r.textContent.toLowerCase().indexOf(f)>-1;
        r.style.display=s?'':'none';if(s)c++;
      }});
      tv.querySelector('.table-count').textContent=c+' de '+rows.length+' linhas';
    }}

    /* ── Ordenação de tabela ─── */
    var _sd={{}};
    function sortTable(th){{
      var col=parseInt(th.dataset.col);
      var tbl=th.closest('table');
      if(!tbl.id)tbl.id='t_'+Math.random().toString(36).slice(2);
      var k=tbl.id+'_'+col;_sd[k]=(_sd[k]||0)===1?-1:1;var d=_sd[k];
      th.closest('thead').querySelectorAll('.sort-arrow').forEach(function(s){{s.textContent='⇅'}});
      th.querySelector('.sort-arrow').textContent=d===1?'↑':'↓';
      var tb=tbl.querySelector('tbody');
      var rows=Array.from(tb.querySelectorAll('tr'));
      rows.sort(function(a,b){{
        var ac=a.cells[col],bc=b.cells[col];
        var an=ac.hasAttribute('data-value')?parseFloat(ac.dataset.value):NaN;
        var bn=bc.hasAttribute('data-value')?parseFloat(bc.dataset.value):NaN;
        if(!isNaN(an)&&!isNaN(bn))return d*(an-bn);
        return d*ac.textContent.trim().localeCompare(bc.textContent.trim(),'pt-BR');
      }});
      rows.forEach(function(r){{tb.appendChild(r)}});
    }}
  </script>
</body>
</html>"""

    saida = PASTA_SAIDA / "mapa_prospecao_cnpjs.html"
    saida.write_text(template, encoding="utf-8")
    logger.info("Dashboard salvo: %s (%.1f MB)", saida.name, saida.stat().st_size / 1024 ** 2)
    return saida


# ─── PREVENT SLEEP ────────────────────────────────────────────────────────────

def _prevent_sleep() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass

def _restore_sleep() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    logger = _setup_logging()
    PASTA_SAIDA.mkdir(exist_ok=True)

    if not ARQUIVO_RESUMO.exists():
        logger.error("Arquivo não encontrado: %s", ARQUIVO_RESUMO)
        logger.error("Execute processar_cnpjs_energia.py e enriquecer_com_tabelas_rf.py primeiro.")
        sys.exit(1)

    _prevent_sleep()
    t0 = time.perf_counter()

    logger.info("=" * 65)
    logger.info("Mapa Interativo de Prospecção — CNPJs × Mercado Livre")
    logger.info("=" * 65)

    try:
        # 1. Carregar e agregar dados CNPJ (df_raw mantido para filtros)
        df_raw   = _carregar_resumo(logger)
        df_mun   = _agregar_por_municipio(df_raw, logger)

        # 2. Geocodificar
        df_ibge  = _carregar_municipios_ibge(logger)
        df_geo   = _geocodificar(df_mun, df_ibge, logger)
        del df_ibge

        # 3. Adicionar população
        df_pop = _carregar_populacao(logger)
        df_pop["codigo_ibge"] = df_pop["codigo_ibge"].astype(str).str.zfill(7)
        df_geo = df_geo.merge(df_pop, on="codigo_ibge", how="left")
        mask_pop = df_geo["populacao"] > 0
        df_geo["tier1_por_1k_hab"] = (
            df_geo["tier1"] * 1000 / df_geo["populacao"]
        ).where(mask_pop)
        del df_pop

        # 4. GeoJSON de todos os municípios
        geojson_todos_path = _geojson_todos(logger)

        # 5. Códigos sem ACL para filtro de oportunidades
        lac_codes: set[str] = set()
        if _GEOJSON_LAC_CACHE.exists():
            with open(_GEOJSON_LAC_CACHE, encoding="utf-8") as _f:
                _gj_lac = json.load(_f)
            lac_codes = {
                str(feat.get("properties", {}).get("codarea", "")).zfill(7)
                for feat in _gj_lac.get("features", [])
            }
            del _gj_lac

        # 6. Preparar dados de filtro (Região / UF / CNAE) e liberar df_raw
        logger.info("--- Preparando dados de filtro ---")
        filtro_dados = _preparar_filtro_dados(df_raw, df_geo, geojson_todos_path, lac_codes, logger)
        del df_raw
        gc.collect()

        # 7. Gerar mapas
        logger.info("--- Gerando mapas ---")

        logger.info("[1/5] Empresas industriais Tier 1 ...")
        html_tier1 = _mapa_coro(
            df_geo, geojson_todos_path,
            coluna="tier1", titulo="Concentração Industrial — Empresas Tier 1 por Município",
            label_cb="Empresas Tier 1", fmt_hover=_fmt_int, logger=logger, use_log=True,
            hover_extra=[
                ("total_empresas", "Total de empresas", _fmt_int),
                ("demanda_MW", "Demanda estimada", _fmt_mw),
            ],
        )

        logger.info("[2/5] Total de empresas (todos os tiers) ...")
        html_total = _mapa_coro(
            df_geo, geojson_todos_path,
            coluna="total_empresas",
            titulo="Total de Empresas em Setores de Alto Consumo por Município",
            label_cb="Total Empresas", fmt_hover=_fmt_int, logger=logger, use_log=True,
            hover_extra=[
                ("tier1", "Tier 1 (industrial)", _fmt_int),
                ("demanda_MW", "Demanda estimada", _fmt_mw),
            ],
        )

        logger.info("[3/5] Demanda potencial estimada ...")
        html_demanda = _mapa_coro(
            df_geo, geojson_todos_path,
            coluna="demanda_MW",
            titulo="Demanda Potencial Estimada por Município (MW)",
            label_cb="MW Estimados", fmt_hover=_fmt_mw, logger=logger, use_log=True,
            hover_extra=[
                ("tier1", "Empresas Tier 1", _fmt_int),
                ("total_empresas", "Total de empresas", _fmt_int),
            ],
        )

        logger.info("[4/5] Densidade Tier 1 por 1.000 habitantes ...")
        html_dens = _mapa_coro(
            df_geo[df_geo["tier1_por_1k_hab"].notna()], geojson_todos_path,
            coluna="tier1_por_1k_hab",
            titulo="Densidade Industrial — Empresas Tier 1 por 1.000 Habitantes",
            label_cb="Emp. Tier 1 / 1k hab", fmt_hover=_fmt_dens, logger=logger, use_log=True,
            hover_extra=[
                ("tier1", "Empresas Tier 1", _fmt_int),
                ("populacao", "Habitantes", _fmt_pop),
            ],
        )

        logger.info("[5/5] Oportunidades (sem ACL + Tier 1) ...")
        html_oport = _mapa_oportunidades(df_geo, geojson_todos_path, logger)

        # 6. Tabelas
        logger.info("[Tabelas] ...")
        df_tbl = df_geo.sort_values("tier1", ascending=False).copy()
        df_tbl["_cidade"] = df_tbl["nome_municipio"].str.title()

        tbl_tier1 = _tabela_html(df_tbl, [
            ("_cidade", "Município", None),
            ("uf", "UF", None),
            ("tier1", "Tier 1", lambda x: _br(int(x))),
            ("total_empresas", "Total Empresas", lambda x: _br(int(x))),
            ("demanda_MW", "Demanda Est. (MW)", lambda x: _br(x, 1)),
            ("populacao", "Habitantes", lambda x: _br(int(x)) if pd.notna(x) and x > 0 else "n/d"),
        ])

        tbl_total = _tabela_html(df_tbl.sort_values("total_empresas", ascending=False), [
            ("_cidade", "Município", None),
            ("uf", "UF", None),
            ("total_empresas", "Total Empresas", lambda x: _br(int(x))),
            ("tier1", "Tier 1", lambda x: _br(int(x))),
            ("tier2", "Tier 2", lambda x: _br(int(x))),
            ("cnae_top", "Setor Dominante", None),
        ])

        tbl_demanda = _tabela_html(df_tbl.sort_values("demanda_MW", ascending=False), [
            ("_cidade", "Município", None),
            ("uf", "UF", None),
            ("demanda_MW", "Demanda Est. (MW)", lambda x: _br(x, 1)),
            ("tier1", "Tier 1", lambda x: _br(int(x))),
            ("cnae_top", "Setor Dominante", None),
        ])

        df_dens_tbl = df_tbl[df_tbl["tier1_por_1k_hab"].notna()].sort_values(
            "tier1_por_1k_hab", ascending=False
        )
        tbl_dens = _tabela_html(df_dens_tbl, [
            ("_cidade", "Município", None),
            ("uf", "UF", None),
            ("tier1_por_1k_hab", "Tier 1 / 1k hab", lambda x: _br(x, 2)),
            ("tier1", "Tier 1", lambda x: _br(int(x))),
            ("populacao", "Habitantes", lambda x: _br(int(x)) if pd.notna(x) and x > 0 else "n/d"),
        ])

        # Tabela de oportunidades (usa lac_codes já calculado)
        df_oport_tbl = (
            df_tbl[df_tbl["codigo_ibge"].isin(lac_codes) & (df_tbl["tier1"] > 0)]
            .sort_values("tier1", ascending=False)
            if lac_codes else df_tbl.head(0)
        )
        tbl_oport = _tabela_html(df_oport_tbl, [
            ("_cidade", "Município", None),
            ("uf", "UF", None),
            ("tier1", "Tier 1", lambda x: _br(int(x))),
            ("total_empresas", "Total Empresas", lambda x: _br(int(x))),
            ("demanda_MW", "Demanda Est. (MW)", lambda x: _br(x, 1)),
            ("populacao", "Habitantes", lambda x: _br(int(x)) if pd.notna(x) and x > 0 else "n/d"),
        ])

        # 8. Salvar dashboard com filtros
        figs = {
            "tier1":   (html_tier1,   tbl_tier1,   "🏭 Indústria Tier 1"),
            "total":   (html_total,   tbl_total,   "🏢 Total de Empresas"),
            "demanda": (html_demanda, tbl_demanda, "⚡ Demanda Potencial"),
            "dens":    (html_dens,    tbl_dens,    "👥 Densidade Industrial"),
            "oport":   (html_oport,   tbl_oport,   "🎯 Oportunidades"),
        }
        saida = _salvar_dashboard(figs, logger, filtro_dados)

        logger.info("=" * 65)
        logger.info("CONCLUÍDO em %.1f s → %s", time.perf_counter() - t0, saida)
        logger.info("=" * 65)

    finally:
        _restore_sleep()


if __name__ == "__main__":
    main()

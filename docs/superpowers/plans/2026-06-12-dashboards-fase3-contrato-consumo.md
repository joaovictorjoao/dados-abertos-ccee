# Dashboards — Fase 3: Contrato de Dados da Seção de Consumo — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Criar `grugeen_dashboards/consumo/contrato.py` que converte os DataFrames da camada de dados (Fase 2a) no **fragmento JSON da seção de consumo** consumido pelo front-end — modelo `registros` crus (o JS calcula escala/filtra ao vivo), conforme a spec.

**Architecture:** Função pura `montar_contrato_consumo(df_per_capita, df_lacunas, referencia, logger) -> dict`. Emite `abas` (definições de exibição), `filtros_proprios` (distribuidora), `registros` (um por município com todas as métricas, NaN→None), `lacunas` (municípios sem ACL) e `municipios_info` (enriquecimento de hover). NÃO pré-computa escalas de cor (isso é responsabilidade do JS). Testado com DataFrames pequenos e asserts sobre o dict resultante (golden). Não toca monólitos; não gera HTML.

**Tech Stack:** Python 3.9+, pandas, numpy, pytest.

**Plano 4 de ~6** (a fase de front-end foi subdividida: contrato → assets/JS → gerador → wiring/seção). Spec: `docs/superpowers/specs/2026-06-11-dashboards-arquitetura-interacao-design.md`. Fases 1, 2a, 2b em `main`.

---

## Contrato-alvo (fragmento da seção consumo)

```python
{
  "label": "Consumo",
  "referencia": "202604",
  "abas": [
    {"id": "estado",    "label": "Por Estado",    "nivel": "uf",        "metrica": "gwh",       "unidade": "GWh",          "escala": "linear"},
    {"id": "municipio", "label": "Por Município",  "nivel": "municipio", "metrica": "gwh",       "unidade": "GWh",          "escala": "log"},
    {"id": "mwh-hab",   "label": "Per Capita",     "nivel": "municipio", "metrica": "mwh_hab",   "unidade": "MWh/hab",      "escala": "log"},
    {"id": "cons-100k", "label": "Penetração ACL", "nivel": "municipio", "metrica": "cons_100k", "unidade": "por 100k hab", "escala": "log"},
    {"id": "lacunas",   "label": "Oportunidades",  "nivel": "municipio", "metrica": "pop",       "unidade": "hab",          "escala": "log", "tipo": "lacuna"}
  ],
  "filtros_proprios": {
    "distribuidora": {"label": "Distribuidora", "depende_de": "uf", "opcoes": ["CELESC", "CPFL", ...]}
  },
  "registros": [
    {"ibge": "4205407", "nome": "Florianópolis", "uf": "SC", "regiao": "Sul",
     "distribuidora": "CELESC", "gwh": 0.5, "mwh_hab": 0.001, "cons_100k": 1.0, "pop": 500000, "nc": 5},
    ...
  ],
  "lacunas": [
    {"ibge": "...", "nome": "...", "uf": "...", "regiao": "...", "pop": 12345}, ...
  ],
  "municipios_info": {
    "4205407": {"nome": "Florianópolis", "uf": "SC", "pop": 500000}, ...
  }
}
```

Regras:
- `registros`: um por município presente em `df_per_capita` (geocodificado, com consumo). `gwh = consumo_total_mwh / 1000`. `mwh_hab`/`cons_100k` podem ser `None` (população ausente) → JS ignora na coloração. `nome` em Title Case a partir da coluna `cidade`.
- `lacunas`: municípios de `df_lacunas` com `populacao > 0`.
- `municipios_info`: união de todos os municípios conhecidos (consumo + lacunas) para hover.
- NaN/inf em floats → `None` (JSON válido).
- `df_per_capita` já vem escopado a UM mês de referência (responsabilidade do entrypoint); a função não itera meses.

> Bordas de estado e GeoJSON NÃO entram no contrato — são assets da camada de geração (plano posterior).

---

## Task 0: Branch
```bash
git checkout main
git checkout -b feat/dashboards-fase3-contrato-consumo
git branch --show-current
```
Expected: `feat/dashboards-fase3-contrato-consumo`.

---

## Task 1: `_limpar_nan` + `_registros` (transformações puras)

**Files:**
- Create: `grugeen_dashboards/consumo/contrato.py`
- Test: `tests/test_contrato_consumo.py`

- [ ] **Step 1: Teste que falha** — `tests/test_contrato_consumo.py`
```python
import logging
import math
import numpy as np
import pandas as pd
from grugeen_dashboards.consumo.contrato import _limpar_nan, _registros

_LOG = logging.getLogger("t")


def test_limpar_nan_converte_nan_e_inf_em_none():
    assert _limpar_nan(float("nan")) is None
    assert _limpar_nan(float("inf")) is None
    assert _limpar_nan(1.5) == 1.5
    assert _limpar_nan({"a": float("nan"), "b": 2}) == {"a": None, "b": 2}
    assert _limpar_nan([1.0, float("nan")]) == [1.0, None]


def _df_pc():
    return pd.DataFrame({
        "codigo_ibge": ["4205407", "3550308"],
        "cidade": ["FLORIANOPOLIS", "SAO PAULO"],
        "uf": ["SC", "SP"],
        "regiao": ["Sul", "Sudeste"],
        "distribuidora": ["CELESC", "CPFL"],
        "consumo_total_mwh": [500.0, 1000.0],
        "n_consumidores": [5, 10],
        "populacao": [500000.0, 1000000.0],
        "mwh_por_habitante": [0.001, 0.001],
        "consumidores_por_100k": [1.0, 1.0],
    })


def test_registros_um_por_municipio_com_metricas():
    regs = _registros(_df_pc())
    assert len(regs) == 2
    flor = next(r for r in regs if r["ibge"] == "4205407")
    assert flor["nome"] == "Florianopolis"   # Title Case
    assert flor["uf"] == "SC"
    assert flor["regiao"] == "Sul"
    assert flor["distribuidora"] == "CELESC"
    assert flor["gwh"] == 0.5                 # 500 mwh / 1000
    assert flor["nc"] == 5
    assert flor["pop"] == 500000


def test_registros_populacao_ausente_metricas_none():
    df = _df_pc()
    df.loc[0, "mwh_por_habitante"] = np.nan
    df.loc[0, "consumidores_por_100k"] = np.nan
    regs = _registros(df)
    flor = next(r for r in regs if r["ibge"] == "4205407")
    assert flor["mwh_hab"] is None
    assert flor["cons_100k"] is None
```

- [ ] **Step 2: Rodar — falha**

Run: `python -m pytest tests/test_contrato_consumo.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar** — `grugeen_dashboards/consumo/contrato.py`
```python
"""Contrato de dados da seção de Consumo: DataFrames → fragmento JSON (registros)."""

import logging
import math

import pandas as pd


def _limpar_nan(obj):
    """Converte NaN/inf (recursivamente) em None, para serialização JSON válida."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _limpar_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_limpar_nan(v) for v in obj]
    return obj


def _num(valor) -> float | None:
    """Float seguro: None se ausente/NaN/inf."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else v


def _registros(df_per_capita: pd.DataFrame) -> list[dict]:
    """Um registro por município, com todas as métricas (NaN → None)."""
    regs: list[dict] = []
    for _, row in df_per_capita.iterrows():
        ibge = str(row.get("codigo_ibge", "")).zfill(7)
        if not ibge or ibge == "0000000":
            continue
        mwh = _num(row.get("consumo_total_mwh"))
        pop = _num(row.get("populacao"))
        regs.append({
            "ibge": ibge,
            "nome": str(row.get("cidade", "")).title(),
            "uf": str(row.get("uf", "")),
            "regiao": str(row.get("regiao", "") or ""),
            "distribuidora": str(row.get("distribuidora", "") or ""),
            "gwh": round(mwh / 1000, 4) if mwh is not None else None,
            "mwh_hab": _num(row.get("mwh_por_habitante")),
            "cons_100k": _num(row.get("consumidores_por_100k")),
            "pop": int(pop) if pop and pop > 0 else 0,
            "nc": int(row.get("n_consumidores") or 0),
        })
    return regs
```

- [ ] **Step 4: Rodar — passa**

Run: `python -m pytest tests/test_contrato_consumo.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/contrato.py" "Mapas de Consumo/tests/test_contrato_consumo.py"
git commit -m "feat: consumo.contrato _registros + _limpar_nan com testes"
```

---

## Task 2: `_lacunas` + `_municipios_info`

**Files:**
- Modify: `grugeen_dashboards/consumo/contrato.py` (append)
- Test: `tests/test_contrato_consumo.py` (append)

- [ ] **Step 1: Append ao teste**
```python
from grugeen_dashboards.consumo.contrato import _lacunas, _municipios_info


def _df_lac():
    return pd.DataFrame({
        "codigo_ibge": ["4204202", "1234567"],
        "nome": ["CHAPECO", "SEM POP"],
        "uf_norm": ["SC", "SC"],
        "regiao": ["Sul", "Sul"],
        "populacao": [200000.0, 0.0],
    })


def test_lacunas_inclui_so_com_populacao():
    lac = _lacunas(_df_lac())
    assert len(lac) == 1
    assert lac[0]["ibge"] == "4204202"
    assert lac[0]["nome"] == "Chapeco"
    assert lac[0]["uf"] == "SC"
    assert lac[0]["pop"] == 200000


def test_lacunas_none_retorna_vazio():
    assert _lacunas(None) == []


def test_municipios_info_une_consumo_e_lacunas():
    info = _municipios_info(_df_pc(), _df_lac())
    assert info["4205407"]["nome"] == "Florianopolis"
    assert info["4205407"]["uf"] == "SC"
    assert info["4204202"]["nome"] == "Chapeco"   # da lacuna
    assert info["1234567"]["pop"] == 0
```

- [ ] **Step 2: Rodar — falha**

Run: `python -m pytest tests/test_contrato_consumo.py -k "lacunas or municipios_info" -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implementar** — append a `contrato.py`:
```python
def _lacunas(df_lacunas: pd.DataFrame | None) -> list[dict]:
    """Municípios sem consumidores ACL, com população > 0."""
    if df_lacunas is None or df_lacunas.empty:
        return []
    out: list[dict] = []
    for _, row in df_lacunas.iterrows():
        ibge = str(row.get("codigo_ibge", "")).zfill(7)
        pop = _num(row.get("populacao"))
        if not ibge or ibge == "0000000" or not pop or pop <= 0:
            continue
        out.append({
            "ibge": ibge,
            "nome": str(row.get("nome", "")).title(),
            "uf": str(row.get("uf_norm", "")),
            "regiao": str(row.get("regiao", "") or ""),
            "pop": int(pop),
        })
    return out


def _municipios_info(
    df_per_capita: pd.DataFrame, df_lacunas: pd.DataFrame | None
) -> dict[str, dict]:
    """Mapa ibge → {nome, uf, pop} para enriquecer hover (consumo + lacunas)."""
    info: dict[str, dict] = {}
    for _, row in df_per_capita.iterrows():
        ibge = str(row.get("codigo_ibge", "")).zfill(7)
        if not ibge or ibge in info:
            continue
        pop = _num(row.get("populacao"))
        info[ibge] = {
            "nome": str(row.get("cidade", "")).title(),
            "uf": str(row.get("uf", "")),
            "pop": int(pop) if pop and pop > 0 else 0,
        }
    if df_lacunas is not None and not df_lacunas.empty:
        for _, row in df_lacunas.iterrows():
            ibge = str(row.get("codigo_ibge", "")).zfill(7)
            if not ibge or ibge in info:
                continue
            pop = _num(row.get("populacao"))
            info[ibge] = {
                "nome": str(row.get("nome", "")).title(),
                "uf": str(row.get("uf_norm", "")),
                "pop": int(pop) if pop and pop > 0 else 0,
            }
    return info
```

- [ ] **Step 4: Rodar — passa**

Run: `python -m pytest tests/test_contrato_consumo.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/contrato.py" "Mapas de Consumo/tests/test_contrato_consumo.py"
git commit -m "feat: consumo.contrato _lacunas + _municipios_info com testes"
```

---

## Task 3: `montar_contrato_consumo` (montagem do fragmento)

**Files:**
- Modify: `grugeen_dashboards/consumo/contrato.py` (append)
- Test: `tests/test_contrato_consumo.py` (append)

- [ ] **Step 1: Append ao teste**
```python
import json
from grugeen_dashboards.consumo.contrato import montar_contrato_consumo


def test_montar_contrato_estrutura_completa():
    c = montar_contrato_consumo(_df_pc(), _df_lac(), "202604", _LOG)
    assert c["label"] == "Consumo"
    assert c["referencia"] == "202604"
    # 5 abas na ordem esperada
    assert [a["id"] for a in c["abas"]] == ["estado", "municipio", "mwh-hab", "cons-100k", "lacunas"]
    assert c["abas"][0]["nivel"] == "uf"
    assert c["abas"][-1]["tipo"] == "lacuna"
    # filtro próprio distribuidora com opções ordenadas
    assert c["filtros_proprios"]["distribuidora"]["depende_de"] == "uf"
    assert c["filtros_proprios"]["distribuidora"]["opcoes"] == ["CELESC", "CPFL"]
    assert len(c["registros"]) == 2
    assert len(c["lacunas"]) == 1
    assert "4205407" in c["municipios_info"]


def test_montar_contrato_e_serializavel_em_json():
    df = _df_pc()
    df.loc[0, "mwh_por_habitante"] = float("nan")
    c = montar_contrato_consumo(df, None, "202604", _LOG)
    # json.dumps não pode levantar (NaN já virou None) com allow_nan=False
    s = json.dumps(c, ensure_ascii=False, allow_nan=False)
    assert '"label":"Consumo"' in s.replace(" ", "")
```

- [ ] **Step 2: Rodar — falha**

Run: `python -m pytest tests/test_contrato_consumo.py -k montar -v`
Expected: FAIL — `ImportError: cannot import name 'montar_contrato_consumo'`.

- [ ] **Step 3: Implementar** — append a `contrato.py`:
```python
_ABAS_CONSUMO: list[dict] = [
    {"id": "estado",    "label": "Por Estado",    "nivel": "uf",        "metrica": "gwh",       "unidade": "GWh",          "escala": "linear"},
    {"id": "municipio", "label": "Por Município",  "nivel": "municipio", "metrica": "gwh",       "unidade": "GWh",          "escala": "log"},
    {"id": "mwh-hab",   "label": "Per Capita",     "nivel": "municipio", "metrica": "mwh_hab",   "unidade": "MWh/hab",      "escala": "log"},
    {"id": "cons-100k", "label": "Penetração ACL", "nivel": "municipio", "metrica": "cons_100k", "unidade": "por 100k hab", "escala": "log"},
    {"id": "lacunas",   "label": "Oportunidades",  "nivel": "municipio", "metrica": "pop",       "unidade": "hab",          "escala": "log", "tipo": "lacuna"},
]


def _opcoes_distribuidora(df_per_capita: pd.DataFrame) -> list[str]:
    if "distribuidora" not in df_per_capita.columns:
        return []
    vals = df_per_capita["distribuidora"].dropna().unique().tolist()
    return sorted(v for v in vals if v)


def montar_contrato_consumo(
    df_per_capita: pd.DataFrame,
    df_lacunas: pd.DataFrame | None,
    referencia: str,
    logger: logging.Logger,
) -> dict:
    """Monta o fragmento JSON da seção de consumo (registros crus; escala fica no JS)."""
    contrato = {
        "label": "Consumo",
        "referencia": str(referencia),
        "abas": [dict(a) for a in _ABAS_CONSUMO],
        "filtros_proprios": {
            "distribuidora": {
                "label": "Distribuidora",
                "depende_de": "uf",
                "opcoes": _opcoes_distribuidora(df_per_capita),
            }
        },
        "registros": _registros(df_per_capita),
        "lacunas": _lacunas(df_lacunas),
        "municipios_info": _municipios_info(df_per_capita, df_lacunas),
    }
    logger.info(
        "Contrato consumo: %d registros, %d lacunas, %d municípios no hover",
        len(contrato["registros"]), len(contrato["lacunas"]),
        len(contrato["municipios_info"]),
    )
    return _limpar_nan(contrato)
```

- [ ] **Step 4: Rodar — passa**

Run: `python -m pytest tests/test_contrato_consumo.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/contrato.py" "Mapas de Consumo/tests/test_contrato_consumo.py"
git commit -m "feat: consumo.contrato.montar_contrato_consumo com testes"
```

---

## Task 4: Suíte completa + verificação

- [ ] **Step 1:** `python -m pytest`
Expected: **58 testes** (49 anteriores + 9 de contrato), zero falhas.

- [ ] **Step 2: Smoke**
Run: `python -c "from grugeen_dashboards.consumo.contrato import montar_contrato_consumo; print('ok')"`
Expected: `ok`.

---

## Self-Review (autor)

- **Decisão registrada:** registros crus; escala/filtragem no JS (confirmado pelo usuário,
  alinhado à spec). Por isso `logMax`/cores NÃO entram no contrato.
- **Parity:** registros derivam dos mesmos campos que `_preparar_filtro_dados_consumo`
  produzia (uf, regiao, dist, gwh, mwh_hab, cons_100k, pop, nc, nome Title Case);
  lacunas e municipios_info idem.
- **JSON válido:** `_limpar_nan` + teste com `allow_nan=False` garantem serialização.
- **Placeholders:** nenhum. **Não-objetivo:** sem HTML/assets/geojson (planos seguintes).

---

## Roadmap restante
- **Plano 5 — Assets do front (template.html + dashboard.css + core/*.js)** com estado central, filtros, render (Plotly.react + uirevision para o bug de zoom), hover, e a barra de filtros geográficos. Testes de lógica de filtro em Node.
- **Plano 6 — Gerador (2 modos de saída) + wiring da seção consumo + comparação com baseline + correção dos bugs de hover/zoom/filtro.**
- **Depois — prospecção como 2ª seção + drill-down cruzado + novos filtros + aposentar monólitos.**

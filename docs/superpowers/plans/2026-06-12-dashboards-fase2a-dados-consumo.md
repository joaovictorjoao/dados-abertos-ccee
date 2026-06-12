# Dashboards — Fase 2a: Camada de Dados do Consumo — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrair a camada de dados do dashboard de consumo para `grugeen_dashboards/consumo/dados.py` — funções de agregação e enriquecimento **puras e parametrizadas**, reaproveitando `comum/`, com testes sobre DataFrames/CSVs pequenos. Move também as constantes geográficas compartilhadas (UF↔IBGE↔região) para `comum/regioes.py`.

**Architecture:** As funções deixam de depender de constantes globais de caminho — recebem caminhos/URLs/separador como argumentos. As transformações puras (per capita, lacunas) são testadas com DataFrames montados à mão; as funções de I/O (DuckDB sobre CSV, downloads) são parametrizadas e testadas com fixtures pequenas (CSV temporário, cache pré-criado, `monkeypatch` de `comum.fetch`). Os aliases de grafia são dados específicos do dataset de consumo e ficam em `consumo/aliases.py`. Esta fase NÃO toca os monólitos nem gera dashboard — entrega uma camada de dados testável de forma independente.

**Tech Stack:** Python 3.9+, pandas, duckdb, pytest. Sem dependências novas.

**Plano 2 de ~5.** Spec: `docs/superpowers/specs/2026-06-11-dashboards-arquitetura-interacao-design.md`. Fase 1 (módulo `comum/`) já concluída e mergeada em `main`.

---

## Estrutura de Arquivos desta Fase

Criados sob `Mapas de Consumo/`:

- `grugeen_dashboards/comum/regioes.py` — `UF_PARA_IBGE`, `IBGE_PARA_UF`, `UF_PARA_REGIAO` (dados de referência compartilhados).
- `grugeen_dashboards/consumo/__init__.py` — marca o subpacote.
- `grugeen_dashboards/consumo/aliases.py` — `ALIASES_CONSUMO` (correções de grafia CCEE→IBGE).
- `grugeen_dashboards/consumo/dados.py` — agregações + enriquecimento.
- `tests/test_regioes.py`, `tests/test_consumo_dados.py`.

> **Comandos:** terminal já em `…/Dados Abertos CCEE/Mapas de Consumo`. Branch de
> trabalho dedicada (criada na Task 0). Nunca usar `git commit --no-verify`
> (hook bloqueia). Sempre citar caminhos entre aspas (espaços/acentos). UTF-8.

---

## Task 0: Branch de trabalho

**Files:** nenhum (operação git).

- [ ] **Step 1: Criar a branch a partir de `main` atualizado**

Run (a partir da raiz do repo, um nível acima de `Mapas de Consumo`):
```bash
git checkout main
git checkout -b feat/dashboards-fase2a-dados-consumo
git branch --show-current
```
Expected: imprime `feat/dashboards-fase2a-dados-consumo`.

> Sem commit nesta task. As tasks seguintes commitam nesta branch.

---

## Task 1: `comum/regioes.py` — constantes geográficas compartilhadas

Origem: `mapa_consumo_mensal.py:96-103` (`_UF_PARA_IBGE`) e `:126-135`
(`_UF_REGIAO` / `_UF_PARA_REGIAO`). São dados usados por consumo E prospecção.

**Files:**
- Create: `grugeen_dashboards/comum/regioes.py`
- Modify: `grugeen_dashboards/comum/__init__.py` (re-export)
- Test: `tests/test_regioes.py`

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_regioes.py`
```python
from grugeen_dashboards.comum.regioes import (
    UF_PARA_IBGE, IBGE_PARA_UF, UF_PARA_REGIAO,
)


def test_27_unidades_federativas():
    assert len(UF_PARA_IBGE) == 27
    assert len(UF_PARA_REGIAO) == 27


def test_uf_para_ibge_valores_conhecidos():
    assert UF_PARA_IBGE["SP"] == "35"
    assert UF_PARA_IBGE["SC"] == "42"
    assert UF_PARA_IBGE["RR"] == "14"


def test_ibge_para_uf_e_inverso():
    assert IBGE_PARA_UF["35"] == "SP"
    assert all(IBGE_PARA_UF[v] == k for k, v in UF_PARA_IBGE.items())


def test_uf_para_regiao():
    assert UF_PARA_REGIAO["SC"] == "Sul"
    assert UF_PARA_REGIAO["BA"] == "Nordeste"
    assert UF_PARA_REGIAO["SP"] == "Sudeste"
    assert UF_PARA_REGIAO["AM"] == "Norte"
    assert UF_PARA_REGIAO["GO"] == "Centro-Oeste"
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_regioes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grugeen_dashboards.comum.regioes'`.

- [ ] **Step 3: Implementar** — `grugeen_dashboards/comum/regioes.py`
```python
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
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python -m pytest tests/test_regioes.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar a linha de import (depois dos imports existentes, antes do `__all__`):
```python
from .regioes import UF_PARA_IBGE, IBGE_PARA_UF, UF_PARA_REGIAO
```
E acrescentar ao `__all__` os três nomes:
```python
    "UF_PARA_IBGE", "IBGE_PARA_UF", "UF_PARA_REGIAO",
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `python -m pytest`
Expected: PASS (28 anteriores + 4 novos = 32).

- [ ] **Step 7: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/regioes.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_regioes.py"
git commit -m "feat: comum.regioes — constantes UF/IBGE/regiao com testes"
```

---

## Task 2: Subpacote `consumo/` + `aliases.py`

**Files:**
- Create: `grugeen_dashboards/consumo/__init__.py`
- Create: `grugeen_dashboards/consumo/aliases.py`

- [ ] **Step 1: Criar `grugeen_dashboards/consumo/__init__.py`**
```python
"""Camada de dados e contrato da seção de Consumo (ACL)."""
```

- [ ] **Step 2: Criar `grugeen_dashboards/consumo/aliases.py`**

Copiar o dicionário `_ALIASES` de `mapa_consumo_mensal.py` (linhas 256–314)
**verbatim**, renomeando a variável para `ALIASES_CONSUMO` e mantendo TODAS as
entradas e comentários de UF. O cabeçalho do arquivo deve ser:
```python
"""Correções de grafia de municípios do CCEE → nome normalizado IBGE (consumo).

Chave: (nome_normalizado_CCEE, UF) → nome_normalizado_IBGE.
Dados específicos do dataset de consumo; não compartilhar com prospecção.
"""

ALIASES_CONSUMO: dict[tuple[str, str], str] = {
    # ... (todas as entradas das linhas 256–314 de mapa_consumo_mensal.py) ...
}
```
Verificação de integridade após copiar:
Run: `python -c "from grugeen_dashboards.consumo.aliases import ALIASES_CONSUMO; print(len(ALIASES_CONSUMO))"`
Expected: imprime o número de entradas (deve ser o mesmo do dict original — confira contando as linhas de par `(...): "..."` no original; é > 40).

- [ ] **Step 3: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/__init__.py" "Mapas de Consumo/grugeen_dashboards/consumo/aliases.py"
git commit -m "feat: subpacote consumo + ALIASES_CONSUMO"
```

---

## Task 3: `consumo/dados.py` — `calcular_per_capita` (transformação pura)

Origem: `mapa_consumo_mensal.py:459-485`. Substitui o global `_UF_PARA_REGIAO`
por import de `comum.regioes`.

**Files:**
- Create: `grugeen_dashboards/consumo/dados.py`
- Test: `tests/test_consumo_dados.py`

- [ ] **Step 1: Escrever o teste que falha** — `tests/test_consumo_dados.py`
```python
import logging
import numpy as np
import pandas as pd
from grugeen_dashboards.consumo.dados import calcular_per_capita

_LOG = logging.getLogger("t")


def _geo():
    return pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407"],   # São Paulo, Florianópolis
        "uf": ["SP", "SC"],
        "consumo_total_mwh": [1000.0, 500.0],
        "n_consumidores": [10, 5],
    })


def _pop():
    return pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407"],
        "populacao": [1_000_000.0, 500_000.0],
    })


def test_per_capita_calcula_mwh_e_consumidores():
    out = calcular_per_capita(_geo(), _pop(), _LOG)
    sp = out[out["codigo_ibge"] == "3550308"].iloc[0]
    assert sp["mwh_por_habitante"] == 0.001            # 1000 / 1_000_000
    assert sp["consumidores_por_100k"] == 1.0          # 10 * 100_000 / 1_000_000
    assert sp["regiao"] == "Sudeste"


def test_per_capita_populacao_zero_ou_ausente_vira_nan():
    geo = _geo()
    pop = pd.DataFrame({"codigo_ibge": ["3550308", "4205407"], "populacao": [0.0, np.nan]})
    out = calcular_per_capita(geo, pop, _LOG)
    assert out["mwh_por_habitante"].isna().all()
    assert out["consumidores_por_100k"].isna().all()


def test_per_capita_cria_coluna_distribuidora_se_ausente():
    out = calcular_per_capita(_geo(), _pop(), _LOG)
    assert "distribuidora" in out.columns
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_consumo_dados.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grugeen_dashboards.consumo.dados'`.

- [ ] **Step 3: Implementar** — criar `grugeen_dashboards/consumo/dados.py` com:
```python
"""Camada de dados da seção de Consumo: agregação e enriquecimento (ACL)."""

import json
import logging
from pathlib import Path

import duckdb
import pandas as pd

from grugeen_dashboards.comum import baixar_recurso, fetch, normalizar
from grugeen_dashboards.comum.regioes import IBGE_PARA_UF, UF_PARA_REGIAO
from grugeen_dashboards.consumo.aliases import ALIASES_CONSUMO


def calcular_per_capita(
    df_geo: pd.DataFrame, df_pop: pd.DataFrame, logger: logging.Logger
) -> pd.DataFrame:
    """Junta consumo geocodificado à população e calcula MWh/hab e consumidores/100k."""
    df = df_geo.copy()
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.strip().str.zfill(7)

    df_p = df_pop[["codigo_ibge", "populacao"]].copy()
    df_p["codigo_ibge"] = df_p["codigo_ibge"].astype(str).str.zfill(7)

    df_merged = df.merge(df_p, on="codigo_ibge", how="left")
    encontrados = int(df_merged["populacao"].notna().sum())
    logger.info(
        "Populacao: %d/%d municípios com dados (%.0f%%)",
        encontrados, len(df_merged),
        100 * encontrados / len(df_merged) if len(df_merged) else 0,
    )

    mask = df_merged["populacao"] > 0
    # .where(mask) mantém float64 nativo — None/object causaria problemas no Plotly
    df_merged["mwh_por_habitante"] = (
        df_merged["consumo_total_mwh"] / df_merged["populacao"]
    ).where(mask)
    df_merged["consumidores_por_100k"] = (
        df_merged["n_consumidores"] * 100_000 / df_merged["populacao"]
    ).where(mask)
    df_merged["regiao"] = df_merged["uf"].map(UF_PARA_REGIAO).fillna("")
    if "distribuidora" not in df_merged.columns:
        df_merged["distribuidora"] = ""
    return df_merged
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python -m pytest tests/test_consumo_dados.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/dados.py" "Mapas de Consumo/tests/test_consumo_dados.py"
git commit -m "feat: consumo.dados.calcular_per_capita com testes"
```

---

## Task 4: `consumo/dados.py` — `calcular_lacunas`

Origem: `mapa_consumo_mensal.py:504-523`.

**Files:**
- Modify: `grugeen_dashboards/consumo/dados.py` (append)
- Test: `tests/test_consumo_dados.py` (append)

- [ ] **Step 1: Append ao teste** — `tests/test_consumo_dados.py`
```python
from grugeen_dashboards.consumo.dados import calcular_lacunas


def _ibge():
    return pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407", "3304557"],  # SP, Floripa, Rio
        "nome": ["São Paulo", "Florianópolis", "Rio de Janeiro"],
        "uf_norm": ["SP", "SC", "RJ"],
    })


def test_lacunas_retorna_municipios_fora_do_dataset_com_populacao():
    pop = pd.DataFrame({
        "codigo_ibge": ["3550308", "4205407", "3304557"],
        "populacao": [1_000_000.0, 500_000.0, 6_000_000.0],
    })
    # dataset ACL só cobre São Paulo → lacunas = Floripa e Rio
    out = calcular_lacunas(_ibge(), pop, {"3550308"}, _LOG)
    assert set(out["codigo_ibge"]) == {"4205407", "3304557"}


def test_lacunas_descarta_sem_populacao():
    pop = pd.DataFrame({
        "codigo_ibge": ["4205407", "3304557"],
        "populacao": [500_000.0, np.nan],
    })
    out = calcular_lacunas(_ibge(), pop, {"3550308"}, _LOG)
    assert set(out["codigo_ibge"]) == {"4205407"}   # Rio cai (pop NaN)
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_consumo_dados.py -k lacunas -v`
Expected: FAIL — `ImportError: cannot import name 'calcular_lacunas'`.

- [ ] **Step 3: Implementar** — append a `grugeen_dashboards/consumo/dados.py`:
```python
def calcular_lacunas(
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
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python -m pytest tests/test_consumo_dados.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/dados.py" "Mapas de Consumo/tests/test_consumo_dados.py"
git commit -m "feat: consumo.dados.calcular_lacunas com testes"
```

---

## Task 5: `consumo/dados.py` — agregação DuckDB parametrizada

Origem: `mapa_consumo_mensal.py:196-244` (`_agregar_por_estado`, `_agregar_por_cidade`).
Recebem o caminho do arquivo e o separador como parâmetros (em vez dos globais
`ARQUIVO_ENTRADA`/`SEPARADOR`), o que os torna testáveis com um CSV pequeno.

**Files:**
- Modify: `grugeen_dashboards/consumo/dados.py` (append)
- Test: `tests/test_consumo_dados.py` (append)

- [ ] **Step 1: Append ao teste** — `tests/test_consumo_dados.py`
```python
from grugeen_dashboards.consumo.dados import agregar_por_estado, agregar_por_cidade


def _csv_consumo(tmp_path):
    # CSV pequeno no formato CCEE (delim ';', ponto decimal)
    p = tmp_path / "mini.csv"
    p.write_text(
        "MES_REFERENCIA;ESTADO_CARGA;CIDADE_CARGA;CNPJ_CARGA;CONSUMO_CARGA_ACL;SIGLA_PERFIL_AGENTE_DISTRIBUIDORA\n"
        "202604;SP;SAO PAULO;111;100.5;CPFL\n"
        "202604;SP;SAO PAULO;222;200.0;CPFL\n"
        "202604;SC;FLORIANOPOLIS;333;50.0;CELESC\n",
        encoding="utf-8",
    )
    return p


def test_agregar_por_estado_soma_e_converte_gwh(tmp_path):
    df = agregar_por_estado(_csv_consumo(tmp_path), ";", _LOG)
    sp = df[df["uf"] == "SP"].iloc[0]
    assert sp["n_consumidores"] == 2
    assert sp["consumo_total_mwh"] == 300.5
    assert abs(sp["consumo_total_gwh"] - 0.3005) < 1e-9


def test_agregar_por_cidade_inclui_distribuidora_dominante(tmp_path):
    df = agregar_por_cidade(_csv_consumo(tmp_path), ";", _LOG)
    sp = df[df["cidade"] == "SAO PAULO"].iloc[0]
    assert sp["uf"] == "SP"
    assert sp["n_consumidores"] == 2
    assert sp["distribuidora"] == "CPFL"
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_consumo_dados.py -k agregar -v`
Expected: FAIL — `ImportError: cannot import name 'agregar_por_estado'`.

- [ ] **Step 3: Implementar** — append a `grugeen_dashboards/consumo/dados.py`:
```python
def agregar_por_estado(
    arquivo_entrada: Path, separador: str, logger: logging.Logger
) -> pd.DataFrame:
    """Soma consumo ACL por UF. O arquivo usa ponto decimal — TRY_CAST direto."""
    arquivo_fwd = str(arquivo_entrada).replace("\\", "/")
    logger.info("Agregando por estado ...")
    sql = f"""
    SELECT
        MES_REFERENCIA,
        TRIM(UPPER(ESTADO_CARGA))        AS uf,
        COUNT(DISTINCT CNPJ_CARGA)       AS n_consumidores,
        SUM(TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE)) AS consumo_total_mwh
    FROM read_csv('{arquivo_fwd}', delim='{separador}', header=true,
                  ignore_errors=true, all_varchar=true)
    WHERE ESTADO_CARGA IS NOT NULL AND TRIM(ESTADO_CARGA) != ''
    GROUP BY MES_REFERENCIA, TRIM(UPPER(ESTADO_CARGA))
    ORDER BY MES_REFERENCIA, uf
    """
    df = duckdb.sql(sql).df()
    df["consumo_total_gwh"] = df["consumo_total_mwh"] / 1_000
    logger.info("  %d estados", len(df))
    return df


def agregar_por_cidade(
    arquivo_entrada: Path, separador: str, logger: logging.Logger
) -> pd.DataFrame:
    """Soma consumo ACL por cidade+UF, incluindo a distribuidora dominante."""
    arquivo_fwd = str(arquivo_entrada).replace("\\", "/")
    logger.info("Agregando por cidade ...")
    sql = f"""
    SELECT
        MES_REFERENCIA,
        TRIM(UPPER(CIDADE_CARGA))        AS cidade,
        TRIM(UPPER(ESTADO_CARGA))        AS uf,
        COUNT(DISTINCT CNPJ_CARGA)       AS n_consumidores,
        SUM(TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE)) AS consumo_total_mwh,
        FIRST(TRIM(UPPER(SIGLA_PERFIL_AGENTE_DISTRIBUIDORA))
              ORDER BY TRY_CAST(CONSUMO_CARGA_ACL AS DOUBLE) DESC NULLS LAST)
              AS distribuidora
    FROM read_csv('{arquivo_fwd}', delim='{separador}', header=true,
                  ignore_errors=true, all_varchar=true)
    WHERE CIDADE_CARGA IS NOT NULL AND TRIM(CIDADE_CARGA) != ''
      AND ESTADO_CARGA IS NOT NULL AND TRIM(ESTADO_CARGA) != ''
    GROUP BY MES_REFERENCIA, TRIM(UPPER(CIDADE_CARGA)), TRIM(UPPER(ESTADO_CARGA))
    ORDER BY consumo_total_mwh DESC NULLS LAST
    """
    df = duckdb.sql(sql).df()
    logger.info("  %d municípios", len(df))
    return df
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python -m pytest tests/test_consumo_dados.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/dados.py" "Mapas de Consumo/tests/test_consumo_dados.py"
git commit -m "feat: consumo.dados agregacao DuckDB parametrizada com testes"
```

---

## Task 6: `consumo/dados.py` — carregamento de municípios, população e cache de distribuidoras

Origem: `mapa_consumo_mensal.py:317-328` (`_carregar_municipios`), `:434-456`
(`_baixar_populacao`), `:488-501` (`_salvar_distribuidoras_cache`). Parametrizadas
com URLs/caminhos; downloads testados via cache pré-criado e `monkeypatch` de
`comum.fetch`.

**Files:**
- Modify: `grugeen_dashboards/consumo/dados.py` (append)
- Test: `tests/test_consumo_dados.py` (append)

- [ ] **Step 1: Append ao teste** — `tests/test_consumo_dados.py`
```python
import grugeen_dashboards.consumo.dados as cdados
from grugeen_dashboards.consumo.dados import (
    carregar_municipios, baixar_populacao, salvar_distribuidoras_cache,
)


def test_carregar_municipios_usa_cache_e_normaliza(tmp_path):
    cache = tmp_path / "municipios.csv"
    cache.write_text(
        "codigo_ibge,nome,codigo_uf,latitude,longitude\n"
        "3550308,São Paulo,35,-23.5,-46.6\n",
        encoding="utf-8",
    )
    df = carregar_municipios("http://ignorado", cache, _LOG)
    row = df.iloc[0]
    assert row["nome_norm"] == "SAO PAULO"
    assert row["uf_norm"] == "SP"
    assert row["codigo_ibge"] == "3550308"
    assert row["latitude"] == -23.5


def test_baixar_populacao_parseia_json_da_api(tmp_path, monkeypatch):
    cache = tmp_path / "pop.csv"
    fake = [{"resultados": [{"series": [
        {"localidade": {"id": "3550308"}, "serie": {"2022": "1000000"}},
    ]}]}]
    import json as _json
    monkeypatch.setattr(cdados, "fetch", lambda url, timeout=30: _json.dumps(fake).encode("utf-8"))
    df = baixar_populacao("http://api", cache, _LOG)
    assert df.iloc[0]["codigo_ibge"] == "3550308"
    assert df.iloc[0]["populacao"] == 1_000_000
    assert cache.exists()  # gravou o cache


def test_salvar_distribuidoras_cache(tmp_path):
    out = tmp_path / "dist.csv"
    geo = pd.DataFrame({
        "codigo_ibge": ["3550308", "3550308", "4205407"],
        "distribuidora": ["cpfl", "cpfl", ""],
    })
    salvar_distribuidoras_cache(geo, out, _LOG)
    saved = pd.read_csv(out, dtype=str)
    assert list(saved["codigo_ibge"]) == ["3550308"]   # dedup + descarta vazio
    assert saved.iloc[0]["distribuidora"] == "CPFL"     # upper
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_consumo_dados.py -k "municipios or populacao or distribuidoras" -v`
Expected: FAIL — `ImportError: cannot import name 'carregar_municipios'`.

- [ ] **Step 3: Implementar** — append a `grugeen_dashboards/consumo/dados.py`:
```python
def carregar_municipios(
    municipios_url: str, cache_path: Path, logger: logging.Logger
) -> pd.DataFrame:
    """Baixa (ou usa cache) a tabela de municípios IBGE e adiciona colunas normalizadas."""
    baixar_recurso(municipios_url, cache_path, logger)
    df = pd.read_csv(cache_path, encoding="utf-8", dtype=str)
    df["nome_norm"] = df["nome"].apply(normalizar)
    df["uf_norm"] = df["codigo_uf"].map(IBGE_PARA_UF)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.strip().str.zfill(7)
    logger.info("Municípios IBGE: %d registros", len(df))
    return df


def baixar_populacao(
    populacao_url: str, cache_path: Path, logger: logging.Logger
) -> pd.DataFrame:
    """População por município (Censo 2022, API IBGE), com cache em CSV."""
    if Path(cache_path).exists():
        logger.info("Cache: %s", Path(cache_path).name)
        df = pd.read_csv(cache_path, dtype=str)
        df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
        return df

    logger.info("Baixando dados do Censo 2022 ...")
    raw = fetch(populacao_url, timeout=30)
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
    df.to_csv(cache_path, index=False, encoding="utf-8")
    df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")
    logger.info("Censo 2022: %d municípios", len(df))
    return df


def salvar_distribuidoras_cache(
    df_geo: pd.DataFrame, cache_path: Path, logger: logging.Logger
) -> None:
    """Salva {codigo_ibge, distribuidora} para compartilhar com a seção de prospecção."""
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
    df.to_csv(cache_path, index=False, encoding="utf-8")
    logger.info("Cache distribuidoras salvo: %d municípios → %s", len(df), Path(cache_path).name)
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python -m pytest tests/test_consumo_dados.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/dados.py" "Mapas de Consumo/tests/test_consumo_dados.py"
git commit -m "feat: consumo.dados carregamento de municipios/populacao/distribuidoras com testes"
```

---

## Task 7: Suíte completa verde

**Files:** verificação apenas.

- [ ] **Step 1: Rodar a suíte completa**

Run: `python -m pytest`
Expected: PASS — **42 testes**, zero falhas. Composição: 28 base (Fase 1) + 4 `regioes` + 10 `consumo_dados` (3 per_capita + 2 lacunas + 2 agregar + 3 carregar/baixar/salvar). Confirmar o total exibido e que `test_consumo_dados.py` e `test_regioes.py` aparecem.

- [ ] **Step 2: Smoke da API de dados de consumo**

Run: `python -c "from grugeen_dashboards.consumo.dados import calcular_per_capita, calcular_lacunas, agregar_por_estado, agregar_por_cidade, carregar_municipios, baixar_populacao, salvar_distribuidoras_cache; print('ok')"`
Expected: imprime `ok`.

- [ ] **Step 3: (sem commit se nada mudou)** — esta task é só verificação.

---

## Self-Review (autor do plano)

- **Cobertura:** a spec coloca `consumo/dados.py` (agregações → DataFrames) e usa
  `comum/geo` (geocodificar) + constantes. Esta fase cobre dados + as constantes
  compartilhadas (regioes). A geocodificação já existe em `comum` (Fase 1) e será
  usada pelo entrypoint na fase de contrato/gerador. `contrato.py` é fase posterior.
- **Placeholders:** o único conteúdo não-literal é o dict `ALIASES_CONSUMO` (Task 2),
  cuja origem exata (linhas 256–314 de `mapa_consumo_mensal.py`) é indicada para cópia
  verbatim + verificação de contagem — instrução concreta, não placeholder.
- **Consistência de nomes:** funções públicas `calcular_per_capita`, `calcular_lacunas`,
  `agregar_por_estado`, `agregar_por_cidade`, `carregar_municipios`, `baixar_populacao`,
  `salvar_distribuidoras_cache`; constantes `UF_PARA_IBGE`, `IBGE_PARA_UF`,
  `UF_PARA_REGIAO`, `ALIASES_CONSUMO`. Usadas de forma idêntica nos testes e imports.
- **Não-objetivo respeitado:** monólitos não são tocados; sem geração de dashboard.

---

## Roadmap restante

- **Plano 3 — `prospeccao/dados.py`** (+ `_DEMANDA_kW`, `ALIASES_PROSPECCAO`,
  `agregar_por_municipio`, `carregar_resumo`, etc.), mesmo padrão.
- **Plano 4 — Contrato + gerador + 1ª seção (consumo) no front.**
- **Plano 5 — 2ª seção (prospecção) + drill-down cruzado + novos filtros + aposentar monólitos.**

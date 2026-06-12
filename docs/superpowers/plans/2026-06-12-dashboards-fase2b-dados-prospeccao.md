# Dashboards — Fase 2b: Camada de Dados da Prospecção — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrair a camada de dados do dashboard de prospecção para `grugeen_dashboards/prospeccao/dados.py`, reaproveitando `comum/`. Como parte disso, **mover os loaders IBGE compartilhados** (`carregar_municipios`, `baixar_populacao`) de `consumo/dados.py` para um novo `comum/ibge.py` (eliminando a duplicação entre as duas seções) e adicionar `carregar_distribuidoras`.

**Architecture:** Loaders de dados IBGE que eram idênticos entre consumo e prospecção passam a viver uma única vez em `comum/ibge.py`. `consumo/dados.py` reaponta para lá via import (mantendo os mesmos nomes — seus testes não mudam). `prospeccao/dados.py` traz as funções específicas (resumo CNAE, agregação por município com tiers/demanda). Constantes específicas: `DEMANDA_kW` e `ALIASES_PROSPECCAO`. Transformações puras testadas com DataFrames/CSVs pequenos. Não toca monólitos; sem geração de dashboard.

**Tech Stack:** Python 3.9+, pandas, pytest. Sem dependências novas.

**Plano 3 de ~5.** Spec: `docs/superpowers/specs/2026-06-11-dashboards-arquitetura-interacao-design.md`. Fases 1 e 2a já em `main`.

---

## Estrutura de Arquivos desta Fase

Sob `Mapas de Consumo/`:
- `grugeen_dashboards/comum/ibge.py` — `carregar_municipios`, `baixar_populacao`, `carregar_distribuidoras` (loaders compartilhados).
- `grugeen_dashboards/consumo/dados.py` — **modificado**: passa a importar os dois loaders de `comum.ibge`.
- `grugeen_dashboards/prospeccao/__init__.py`
- `grugeen_dashboards/prospeccao/aliases.py` — `ALIASES_PROSPECCAO`.
- `grugeen_dashboards/prospeccao/constantes.py` — `DEMANDA_kW`.
- `grugeen_dashboards/prospeccao/dados.py` — `carregar_resumo`, `agregar_por_municipio`.
- `tests/test_ibge.py`, `tests/test_prospeccao_dados.py`.

> Terminal já em `…/Dados Abertos CCEE/Mapas de Consumo`. Nunca `--no-verify`. Aspas em
> caminhos. UTF-8.

---

## Task 0: Branch de trabalho

- [ ] **Step 1:** a partir da raiz do repo:
```bash
git checkout main
git checkout -b feat/dashboards-fase2b-dados-prospeccao
git branch --show-current
```
Expected: `feat/dashboards-fase2b-dados-prospeccao`.

---

## Task 1: `comum/ibge.py` — loaders IBGE compartilhados

`carregar_municipios` e `baixar_populacao` são copiados de `consumo/dados.py` (lá são
idênticos). `carregar_distribuidoras` lê o cache `{codigo_ibge: distribuidora}` que
`consumo.dados.salvar_distribuidoras_cache` grava.

**Files:**
- Create: `grugeen_dashboards/comum/ibge.py`
- Modify: `grugeen_dashboards/comum/__init__.py`
- Test: `tests/test_ibge.py`

- [ ] **Step 1: Teste que falha** — `tests/test_ibge.py`
```python
import json as _json
import logging
import pandas as pd
import grugeen_dashboards.comum.ibge as ibge
from grugeen_dashboards.comum.ibge import (
    carregar_municipios, baixar_populacao, carregar_distribuidoras,
)

_LOG = logging.getLogger("t")


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


def test_baixar_populacao_parseia_json(tmp_path, monkeypatch):
    cache = tmp_path / "pop.csv"
    fake = [{"resultados": [{"series": [
        {"localidade": {"id": "3550308"}, "serie": {"2022": "1000000"}},
    ]}]}]
    monkeypatch.setattr(ibge, "fetch", lambda url, timeout=30: _json.dumps(fake).encode("utf-8"))
    df = baixar_populacao("http://api", cache, _LOG)
    assert df.iloc[0]["codigo_ibge"] == "3550308"
    assert df.iloc[0]["populacao"] == 1_000_000
    assert cache.exists()


def test_carregar_distribuidoras_le_cache_para_dict(tmp_path):
    cache = tmp_path / "dist.csv"
    cache.write_text(
        "codigo_ibge,distribuidora\n3550308,cpfl\n4205407,celesc\n",
        encoding="utf-8",
    )
    mapping = carregar_distribuidoras(cache, _LOG)
    assert mapping["3550308"] == "CPFL"     # zfill + upper
    assert mapping["4205407"] == "CELESC"


def test_carregar_distribuidoras_ausente_retorna_vazio(tmp_path):
    assert carregar_distribuidoras(tmp_path / "nao_existe.csv", _LOG) == {}
```

- [ ] **Step 2: Rodar — falha**

Run: `python -m pytest tests/test_ibge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grugeen_dashboards.comum.ibge'`.

- [ ] **Step 3: Implementar** — `grugeen_dashboards/comum/ibge.py`
```python
"""Loaders de dados de referência do IBGE, compartilhados entre as seções."""

import json
import logging
from pathlib import Path

import pandas as pd

from grugeen_dashboards.comum.http import baixar_recurso, fetch
from grugeen_dashboards.comum.geo import normalizar
from grugeen_dashboards.comum.regioes import IBGE_PARA_UF


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


def carregar_distribuidoras(cache_path: Path, logger: logging.Logger) -> dict[str, str]:
    """Lê o cache {codigo_ibge: distribuidora} (gerado pela seção de consumo)."""
    if not Path(cache_path).exists():
        logger.info("Cache distribuidoras não encontrado (gere pela seção de consumo)")
        return {}
    try:
        df = pd.read_csv(cache_path, dtype=str, encoding="utf-8")
        df["codigo_ibge"] = df["codigo_ibge"].astype(str).str.zfill(7)
        mapping = dict(zip(df["codigo_ibge"], df["distribuidora"].fillna("").str.upper()))
        logger.info("Distribuidoras: %d municípios carregados", len(mapping))
        return mapping
    except Exception as exc:
        logger.warning("Erro ao carregar distribuidoras: %s", exc)
        return {}
```

- [ ] **Step 4: Rodar — passa**

Run: `python -m pytest tests/test_ibge.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar import após o de `regioes`:
```python
from .ibge import carregar_municipios, baixar_populacao, carregar_distribuidoras
```
E ao `__all__`:
```python
    "carregar_municipios", "baixar_populacao", "carregar_distribuidoras",
```

- [ ] **Step 6: Suíte**

Run: `python -m pytest`
Expected: 42 + 4 = 46 passed.

- [ ] **Step 7: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/ibge.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_ibge.py"
git commit -m "feat: comum.ibge — loaders municipios/populacao/distribuidoras compartilhados"
```

---

## Task 2: Reapontar `consumo/dados.py` para os loaders compartilhados (DRY)

Remove as definições locais de `carregar_municipios` e `baixar_populacao` de
`consumo/dados.py` e passa a importá-las de `comum.ibge`, reexportando os mesmos nomes
(para os testes de consumo continuarem válidos sem alteração). Remove imports que
ficam sem uso.

**Files:**
- Modify: `grugeen_dashboards/consumo/dados.py`

- [ ] **Step 1: Editar `consumo/dados.py`**

(a) Substituir o bloco de imports atual:
```python
import json
import logging
from pathlib import Path

import duckdb
import pandas as pd

from grugeen_dashboards.comum import baixar_recurso, fetch, normalizar
from grugeen_dashboards.comum.regioes import IBGE_PARA_UF, UF_PARA_REGIAO
```
por:
```python
import logging
from pathlib import Path

import duckdb
import pandas as pd

from grugeen_dashboards.comum.regioes import UF_PARA_REGIAO
# Loaders IBGE compartilhados — reexportados aqui para a API da seção de consumo.
from grugeen_dashboards.comum.ibge import carregar_municipios, baixar_populacao
```

(b) REMOVER por completo as duas funções `carregar_municipios(...)` e
`baixar_populacao(...)` definidas em `consumo/dados.py` (agora vêm de `comum.ibge`).
Manter `calcular_per_capita`, `calcular_lacunas`, `agregar_por_estado`,
`agregar_por_cidade`, `salvar_distribuidoras_cache`.

> Após a edição, `json`, `fetch`, `baixar_recurso`, `normalizar`, `IBGE_PARA_UF` não são
> mais usados em `consumo/dados.py` — por isso saíram dos imports. `carregar_municipios`
> e `baixar_populacao` continuam importáveis de `grugeen_dashboards.consumo.dados`
> (reexport), então os testes de consumo NÃO mudam.

- [ ] **Step 2: Verificar que nada quebrou** (testes de consumo usam os nomes reexportados)

Run: `python -m pytest tests/test_consumo_dados.py -v`
Expected: PASS (10 passed) — incluindo os testes de `carregar_municipios`/`baixar_populacao`, agora exercitando a implementação de `comum.ibge` via reexport.

- [ ] **Step 3: Conferir ausência de import morto**

Run: `python -c "import ast,sys; src=open('grugeen_dashboards/consumo/dados.py',encoding='utf-8').read(); print('json' not in src.split('def ')[0] or 'json.' in src)"`
(Verificação simples; o essencial é a suíte completa no Step 4.)

- [ ] **Step 4: Suíte completa**

Run: `python -m pytest`
Expected: 46 passed (sem novas falhas).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/consumo/dados.py"
git commit -m "refactor: consumo.dados reusa loaders IBGE de comum.ibge (DRY)"
```

---

## Task 3: Subpacote `prospeccao/` + constantes (`DEMANDA_kW`, `ALIASES_PROSPECCAO`)

**Files:**
- Create: `grugeen_dashboards/prospeccao/__init__.py`
- Create: `grugeen_dashboards/prospeccao/constantes.py`
- Create: `grugeen_dashboards/prospeccao/aliases.py`

- [ ] **Step 1:** `grugeen_dashboards/prospeccao/__init__.py`:
```python
"""Camada de dados e contrato da seção de Prospecção (CNPJs)."""
```

- [ ] **Step 2:** `grugeen_dashboards/prospeccao/constantes.py` (copiar de
`mapa_prospecao_cnpjs.py:115-129`, renomear para `DEMANDA_kW`):
```python
"""Demanda média estimada por divisão CNAE (kW por estabelecimento)."""

DEMANDA_kW: dict[str, int] = {
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
```

- [ ] **Step 3:** `grugeen_dashboards/prospeccao/aliases.py` (apóstrofos ASCII U+0027):
```python
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
```

- [ ] **Step 4: Verificar integridade**

Run: `python -c "from grugeen_dashboards.prospeccao.constantes import DEMANDA_kW; from grugeen_dashboards.prospeccao.aliases import ALIASES_PROSPECCAO; print(len(DEMANDA_kW), len(ALIASES_PROSPECCAO))"`
Expected: `50 30`.

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/prospeccao/__init__.py" "Mapas de Consumo/grugeen_dashboards/prospeccao/constantes.py" "Mapas de Consumo/grugeen_dashboards/prospeccao/aliases.py"
git commit -m "feat: subpacote prospeccao + DEMANDA_kW + ALIASES_PROSPECCAO"
```

---

## Task 4: `prospeccao/dados.py` — `carregar_resumo`

Origem: `mapa_prospecao_cnpjs.py:239-247`. Parametrizada com o caminho do CSV de resumo.

**Files:**
- Create: `grugeen_dashboards/prospeccao/dados.py`
- Test: `tests/test_prospeccao_dados.py`

- [ ] **Step 1: Teste que falha** — `tests/test_prospeccao_dados.py`
```python
import logging
import pandas as pd
from grugeen_dashboards.prospeccao.dados import carregar_resumo

_LOG = logging.getLogger("t")


def _csv_resumo(tmp_path):
    p = tmp_path / "resumo.csv"
    p.write_text(
        "uf;nome_municipio;cnae_divisao;cnae_descricao;cnae_tier;total_empresas;matrizes\n"
        "SP;SAO PAULO;24;Metalurgia;1;10;8\n"
        "SP;SAO PAULO;47;Varejo;3;100;90\n",
        encoding="utf-8-sig",
    )
    return p


def test_carregar_resumo_converte_numeros_e_calcula_demanda(tmp_path):
    df = carregar_resumo(_csv_resumo(tmp_path), _LOG)
    metal = df[df["cnae_divisao"] == "24"].iloc[0]
    # demanda_kW = DEMANDA_kW["24"] (3000) * total_empresas (10) = 30000
    assert metal["total_empresas"] == 10
    assert metal["demanda_kW"] == 30000
    assert metal["cnae_tier"] == 1


def test_carregar_resumo_divisao_desconhecida_usa_300(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text(
        "uf;nome_municipio;cnae_divisao;cnae_descricao;cnae_tier;total_empresas;matrizes\n"
        "SP;X;99;Desconhecido;3;2;1\n",
        encoding="utf-8-sig",
    )
    df = carregar_resumo(p, _LOG)
    assert df.iloc[0]["demanda_kW"] == 600   # 300 fallback * 2
```

- [ ] **Step 2: Rodar — falha**

Run: `python -m pytest tests/test_prospeccao_dados.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar** — `grugeen_dashboards/prospeccao/dados.py`
```python
"""Camada de dados da seção de Prospecção: resumo CNAE e agregação por município."""

import logging
from pathlib import Path

import pandas as pd

from grugeen_dashboards.comum.geo import normalizar
from grugeen_dashboards.comum.regioes import UF_PARA_REGIAO
from grugeen_dashboards.prospeccao.aliases import ALIASES_PROSPECCAO
from grugeen_dashboards.prospeccao.constantes import DEMANDA_kW


def carregar_resumo(arquivo_resumo: Path, logger: logging.Logger) -> pd.DataFrame:
    """Lê o CSV resumo município×CNAE e calcula a demanda estimada (kW)."""
    logger.info("Carregando %s ...", Path(arquivo_resumo).name)
    df = pd.read_csv(arquivo_resumo, sep=";", dtype=str, encoding="utf-8-sig")
    df["total_empresas"] = pd.to_numeric(df["total_empresas"], errors="coerce").fillna(0)
    df["matrizes"] = pd.to_numeric(df["matrizes"], errors="coerce").fillna(0)
    df["cnae_tier"] = pd.to_numeric(df["cnae_tier"], errors="coerce").fillna(3)
    df["demanda_kW"] = df["cnae_divisao"].map(DEMANDA_kW).fillna(300) * df["total_empresas"]
    logger.info("  %d linhas (combinações município × CNAE)", len(df))
    return df
```

- [ ] **Step 4: Rodar — passa**

Run: `python -m pytest tests/test_prospeccao_dados.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/prospeccao/dados.py" "Mapas de Consumo/tests/test_prospeccao_dados.py"
git commit -m "feat: prospeccao.dados.carregar_resumo com testes"
```

---

## Task 5: `prospeccao/dados.py` — `agregar_por_municipio`

Origem: `mapa_prospecao_cnpjs.py:250-272`. Substitui globais `_normalizar`,
`_ALIASES`, `_UF_PARA_REGIAO` por imports de `comum`/`prospeccao`.

**Files:**
- Modify: `grugeen_dashboards/prospeccao/dados.py` (append)
- Test: `tests/test_prospeccao_dados.py` (append)

- [ ] **Step 1: Append ao teste**
```python
from grugeen_dashboards.prospeccao.dados import agregar_por_municipio


def _resumo_df():
    return pd.DataFrame({
        "uf": ["SP", "SP", "SP"],
        "nome_municipio": ["São Paulo", "São Paulo", "São Paulo"],
        "cnae_divisao": ["24", "47", "10"],
        "cnae_descricao": ["Metalurgia", "Varejo", "Alimentos"],
        "cnae_tier": [1, 3, 1],
        "total_empresas": [10, 100, 5],
        "demanda_kW": [30000.0, 30000.0, 3000.0],
    })


def test_agregar_por_municipio_soma_tiers_e_demanda():
    out = agregar_por_municipio(_resumo_df(), _LOG)
    row = out.iloc[0]
    assert row["total_empresas"] == 115
    assert row["tier1"] == 15           # 10 (metal) + 5 (alimentos)
    assert row["tier2"] == 0
    assert abs(row["demanda_MW"] - 63.0) < 1e-9   # (30000+30000+3000)/1000
    assert row["cnae_top"] == "Varejo"  # maior total_empresas (100)
    assert row["regiao"] == "Sudeste"
    assert row["nome_norm"] == "SAO PAULO"
```

- [ ] **Step 2: Rodar — falha**

Run: `python -m pytest tests/test_prospeccao_dados.py -k agregar -v`
Expected: FAIL — `ImportError: cannot import name 'agregar_por_municipio'`.

- [ ] **Step 3: Implementar** — append a `grugeen_dashboards/prospeccao/dados.py`:
```python
def agregar_por_municipio(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Agrega todas as divisões CNAE por município (tiers, demanda MW, CNAE dominante)."""
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
    agg["nome_norm"] = agg["nome_municipio"].apply(normalizar)
    agg["nome_norm"] = agg.apply(
        lambda r: ALIASES_PROSPECCAO.get((r["nome_norm"], r["uf"]), r["nome_norm"]), axis=1
    )
    agg["regiao"] = agg["uf"].map(UF_PARA_REGIAO).fillna("")
    logger.info("  %d municípios únicos", len(agg))
    return agg
```

- [ ] **Step 4: Rodar — passa**

Run: `python -m pytest tests/test_prospeccao_dados.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**
```bash
git add "Mapas de Consumo/grugeen_dashboards/prospeccao/dados.py" "Mapas de Consumo/tests/test_prospeccao_dados.py"
git commit -m "feat: prospeccao.dados.agregar_por_municipio com testes"
```

---

## Task 6: Suíte completa + verificação

- [ ] **Step 1:** `python -m pytest`
Expected: **49 testes** (46 após Task 1 + Task 2 sem novos; +2 carregar_resumo +1 agregar = 49). Zero falhas.

- [ ] **Step 2: Smoke**
Run: `python -c "from grugeen_dashboards.prospeccao.dados import carregar_resumo, agregar_por_municipio; from grugeen_dashboards.comum import carregar_municipios, baixar_populacao, carregar_distribuidoras; print('ok')"`
Expected: `ok`.

---

## Self-Review (autor)

- **DRY:** loaders IBGE deduplicados em `comum.ibge`; consumo reaponta sem quebrar testes
  (reexport). Esse era o objetivo central — cumprido.
- **Parity:** `carregar_resumo` e `agregar_por_municipio` preservam a lógica do legado
  (tiers via filtro de `cnae_tier`, `demanda_MW = soma(demanda_kW)/1000`, `cnae_top`
  idxmax, normalização + aliases + região).
- **Placeholders:** nenhum — constantes e aliases inline (50 divisões CNAE e 30 aliases),
  com verificação de contagem.
- **Não-objetivo:** monólitos intactos; geocodificação fica para o entrypoint (usará
  `comum.geocodificar` com `coluna_local="nome_municipio"` e `ALIASES_PROSPECCAO`).

---

## Roadmap restante
- **Plano 4 — Contrato + gerador + 1ª seção (consumo) no front** (corrige hover/zoom/filtro com JS testável).
- **Plano 5 — 2ª seção (prospecção) + drill-down cruzado + novos filtros + aposentar monólitos.**

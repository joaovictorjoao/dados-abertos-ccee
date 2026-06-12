# Dashboards — Fase 1: Fundação (pacote `grugeen_dashboards` + módulo `comum/`) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o pacote Python `grugeen_dashboards` com um módulo `comum/` totalmente testado que consolida, sem duplicação, as funções auxiliares hoje copiadas entre `mapa_consumo_mensal.py` e `mapa_prospecao_cnpjs.py`.

**Architecture:** Camada compartilhada de funções **puras e parametrizadas** (sem constantes globais de caminho), organizada por responsabilidade (`formato`, `geo`, `http`, `logging_setup`, `marca`, `energia`). Cada módulo é pequeno e focado, validado por testes `pytest` com valores golden calculados à mão. Esta fase NÃO reescreve os monólitos atuais (serão substituídos quando o consumo virar uma seção, na Fase 3) — entrega uma biblioteca testável de forma independente.

**Tech Stack:** Python 3.9+, pandas, pytest. Sem dependências novas além de `pytest` (dev).

**Plano 1 de ~5** (roadmap completo na seção final). Referência da spec: `docs/superpowers/specs/2026-06-11-dashboards-arquitetura-interacao-design.md`.

---

## Estrutura de Arquivos desta Fase

Criados sob `Mapas de Consumo/`:

- `grugeen_dashboards/__init__.py` — marca o pacote.
- `grugeen_dashboards/comum/__init__.py` — reexporta a API pública do módulo comum.
- `grugeen_dashboards/comum/formato.py` — `formatar_br` e formatadores pt-BR (puro).
- `grugeen_dashboards/comum/geo.py` — `normalizar` e `geocodificar` (parametrizado).
- `grugeen_dashboards/comum/http.py` — `fetch` (detecção gzip) e `baixar_recurso`.
- `grugeen_dashboards/comum/logging_setup.py` — `setup_logging` (prefixo + pastas por parâmetro).
- `grugeen_dashboards/comum/marca.py` — `logo_data_uri` (caminho por parâmetro).
- `grugeen_dashboards/comum/energia.py` — `prevent_sleep` / `restore_sleep`.
- `tests/__init__.py` — vazio.
- `tests/test_formato.py`, `tests/test_geo.py`, `tests/test_http.py`,
  `tests/test_logging_setup.py`, `tests/test_marca.py`, `tests/test_energia.py`.
- `pytest.ini` — configura descoberta de testes a partir de `Mapas de Consumo/`.

> **Nota de comandos:** o diretório de trabalho contém espaços e acentos. Todos os
> comandos abaixo assumem que o terminal já está em
> `…/Dados Abertos CCEE/Mapas de Consumo`. No PowerShell, use aspas no `Set-Location`
> se precisar navegar manualmente.

---

## Task 0: Esqueleto do pacote e configuração de testes

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/__init__.py`
- Create: `Mapas de Consumo/grugeen_dashboards/comum/__init__.py`
- Create: `Mapas de Consumo/tests/__init__.py`
- Create: `Mapas de Consumo/pytest.ini`

- [ ] **Step 1: Criar os diretórios e arquivos `__init__.py`**

Conteúdo de `grugeen_dashboards/__init__.py`:

```python
"""Pacote de geração dos dashboards Grugeen (consumo + prospecção)."""

__all__ = ["comum"]
```

Conteúdo de `grugeen_dashboards/comum/__init__.py` (será preenchido nas tasks seguintes; começa vazio com docstring):

```python
"""Funções auxiliares compartilhadas entre as seções do dashboard."""
```

Conteúdo de `tests/__init__.py`: arquivo vazio (uma linha em branco).

- [ ] **Step 2: Criar `pytest.ini`**

`Mapas de Consumo/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v
markers =
    unit: testes unitários puros
```

- [ ] **Step 3: Garantir o pytest instalado**

Run: `python -m pytest --version`
Expected: imprime a versão (ex.: `pytest 8.x`). Se falhar com "No module named pytest", rode `python -m pip install pytest` e repita.

- [ ] **Step 4: Rodar a suíte vazia para validar a descoberta**

Run: `python -m pytest`
Expected: `no tests ran` (ou "collected 0 items") — sem erros de configuração.

- [ ] **Step 5: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards" "Mapas de Consumo/tests" "Mapas de Consumo/pytest.ini"
git commit -m "chore: esqueleto do pacote grugeen_dashboards e config de testes"
```

---

## Task 1: `formato.py` — formatação numérica pt-BR

Origem: `mapa_consumo_mensal.py:528-547` (`_br`, `_fmt_*`). O `_br` é idêntico nos dois
scripts; é a base. Os formatadores específicos de unidade são consolidados aqui.

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/comum/formato.py`
- Test: `Mapas de Consumo/tests/test_formato.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_formato.py`:

```python
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
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_formato.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grugeen_dashboards.comum.formato'`.

- [ ] **Step 3: Implementar o mínimo para passar**

`grugeen_dashboards/comum/formato.py`:

```python
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
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_formato.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar ao final de `grugeen_dashboards/comum/__init__.py`:

```python
from .formato import (
    formatar_br, fmt_gwh, fmt_mwh, fmt_mwh_hab, fmt_cons_100k, fmt_pop,
)
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/formato.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_formato.py"
git commit -m "feat: comum.formato — formatacao numerica pt-BR com testes"
```

---

## Task 2: `geo.py` — normalização de nomes

Origem: `mapa_prospecao_cnpjs.py:181-187` (versão **superset**, com unificação de
apóstrofos) — escolhida por ser a mais completa. A versão de consumo
(`mapa_consumo_mensal.py:249-252`) é um subconjunto.

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/comum/geo.py`
- Test: `Mapas de Consumo/tests/test_geo.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_geo.py`:

```python
from grugeen_dashboards.comum.geo import normalizar


def test_normalizar_remove_acentos_e_caixa_alta():
    assert normalizar("São Paulo") == "SAO PAULO"


def test_normalizar_colapsa_espacos_duplos():
    assert normalizar("RIO   DE  JANEIRO") == "RIO DE JANEIRO"


def test_normalizar_unifica_apostrofos():
    # aspas curva, modifier letter e acento agudo viram apóstrofo reto
    assert normalizar("Dias d’Avila") == "DIAS D'AVILA"
    assert normalizar("Olhos d´Agua") == "OLHOS D'AGUA"


def test_normalizar_aceita_nao_string():
    assert normalizar(123) == "123"
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_geo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grugeen_dashboards.comum.geo'`.

- [ ] **Step 3: Implementar o mínimo para passar**

`grugeen_dashboards/comum/geo.py`:

```python
"""Normalização de nomes de municípios e geocodificação contra a tabela IBGE."""

import re
import unicodedata

import pandas as pd

# Variantes de apóstrofo (curly quotes, modifier letter, acento agudo, crase) → '
_APOSTROFOS = ("‘", "’", "ʼ", "´", "`")


def normalizar(texto: object) -> str:
    """Maiúsculas, sem acentos, apóstrofos unificados e espaços colapsados."""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()
    for apos in _APOSTROFOS:
        s = s.replace(apos, "'")
    return re.sub(r" {2,}", " ", s)
```

> Observação: `´` (acento agudo) é removido por `unicodedata.combining` em alguns
> contextos, mas quando aparece como caractere isolado (não combinante) o `replace`
> garante a conversão para `'`. O teste cobre exatamente esse caso.

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_geo.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar:

```python
from .geo import normalizar
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/geo.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_geo.py"
git commit -m "feat: comum.geo.normalizar — normalizacao de nomes com testes"
```

---

## Task 3: `geo.py` — geocodificação parametrizada

Origem: `mapa_consumo_mensal.py:331-361` (`_geocodificar`). Generalizada para receber o
nome da coluna do local (`"cidade"` no consumo, `"municipio"` na prospecção) e o dict de
aliases como parâmetro (cada seção tem o seu — NÃO é compartilhado).

**Files:**
- Modify: `Mapas de Consumo/grugeen_dashboards/comum/geo.py`
- Test: `Mapas de Consumo/tests/test_geo.py` (adicionar)

- [ ] **Step 1: Escrever o teste que falha**

Adicionar a `tests/test_geo.py`:

```python
import logging
import pandas as pd
from grugeen_dashboards.comum.geo import geocodificar


def _municipios_fake():
    return pd.DataFrame({
        "nome_norm": ["SAO PAULO", "DIAS D'AVILA"],
        "uf_norm":   ["SP", "BA"],
        "latitude":  [-23.5, -12.6],
        "longitude": [-46.6, -38.3],
        "codigo_ibge": ["3550308", "2910057"],
    })


def test_geocodificar_casa_por_nome_e_uf():
    df = pd.DataFrame({"cidade": ["São Paulo"], "uf": ["SP"]})
    out = geocodificar(df, _municipios_fake(), "cidade", {}, logging.getLogger("t"))
    assert len(out) == 1
    assert out.iloc[0]["codigo_ibge"] == "3550308"


def test_geocodificar_aplica_alias():
    df = pd.DataFrame({"cidade": ["DIAS D AVILA"], "uf": ["BA"]})
    aliases = {("DIAS D AVILA", "BA"): "DIAS D'AVILA"}
    out = geocodificar(df, _municipios_fake(), "cidade", aliases, logging.getLogger("t"))
    assert len(out) == 1
    assert out.iloc[0]["codigo_ibge"] == "2910057"


def test_geocodificar_descarta_sem_coordenada():
    df = pd.DataFrame({"cidade": ["Cidade Inexistente"], "uf": ["SP"]})
    out = geocodificar(df, _municipios_fake(), "cidade", {}, logging.getLogger("t"))
    assert len(out) == 0
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_geo.py -k geocodificar -v`
Expected: FAIL — `ImportError: cannot import name 'geocodificar'`.

- [ ] **Step 3: Implementar o mínimo para passar**

Adicionar a `grugeen_dashboards/comum/geo.py`:

```python
import logging


def geocodificar(
    df_local: pd.DataFrame,
    df_municipios: pd.DataFrame,
    coluna_local: str,
    aliases: dict[tuple[str, str], str],
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Casa `df_local[coluna_local]` + `df_local["uf"]` contra a tabela IBGE
    (`df_municipios` com colunas nome_norm, uf_norm, latitude, longitude,
    codigo_ibge). `aliases` corrige variações de grafia (chave normalizada +
    UF → nome IBGE normalizado). Retorna só as linhas com coordenada encontrada.
    """
    df = df_local.copy()
    df["local_norm"] = df[coluna_local].apply(normalizar)
    df["local_norm"] = df.apply(
        lambda r: aliases.get((r["local_norm"], r["uf"]), r["local_norm"]), axis=1
    )

    lookup = df_municipios[["nome_norm", "uf_norm", "latitude", "longitude", "codigo_ibge"]]
    df_merged = df.merge(
        lookup,
        left_on=["local_norm", "uf"],
        right_on=["nome_norm", "uf_norm"],
        how="left",
    )

    total = len(df_merged)
    encontradas = int(df_merged["latitude"].notna().sum())
    logger.info(
        "Geocodificação: %d/%d locais (%.0f%%)",
        encontradas, total, 100 * encontradas / total if total else 0,
    )
    sem = df_merged[df_merged["latitude"].isna()][coluna_local].unique()
    if len(sem):
        logger.warning(
            "Sem coords (%d): %s%s",
            len(sem), ", ".join(map(str, sem[:8])), " ..." if len(sem) > 8 else "",
        )
    return df_merged.dropna(subset=["latitude", "longitude"]).copy()
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_geo.py -v`
Expected: PASS (todos, incluindo os 3 novos).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Atualizar a linha de import de geo para:

```python
from .geo import normalizar, geocodificar
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/geo.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_geo.py"
git commit -m "feat: comum.geo.geocodificar parametrizada com testes"
```

---

## Task 4: `http.py` — download com detecção de gzip

Origem: `mapa_consumo_mensal.py:170-191` (`_fetch`, `_baixar_recurso`). Unifica as duas
versões mantendo o `try/except` com log de erro do `_baixar_recurso` de consumo.

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/comum/http.py`
- Test: `Mapas de Consumo/tests/test_http.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_http.py`:

```python
import gzip
import io
import logging
import pytest
from grugeen_dashboards.comum import http


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data
    def read(self):
        return self._data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_fetch_descomprime_gzip(monkeypatch):
    payload = b"conteudo original"
    comprimido = gzip.compress(payload)
    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda req, timeout=30: _FakeResp(comprimido))
    assert http.fetch("http://x") == payload


def test_fetch_passa_bytes_crus_quando_nao_gzip(monkeypatch):
    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda req, timeout=30: _FakeResp(b"texto puro"))
    assert http.fetch("http://x") == b"texto puro"


def test_baixar_recurso_usa_cache_existente(tmp_path, monkeypatch):
    destino = tmp_path / "arq.bin"
    destino.write_bytes(b"ja existe")
    def _boom(*a, **k):
        raise AssertionError("não deveria baixar quando há cache")
    monkeypatch.setattr(http, "fetch", _boom)
    http.baixar_recurso("http://x", destino, logging.getLogger("t"))
    assert destino.read_bytes() == b"ja existe"


def test_baixar_recurso_grava_quando_ausente(tmp_path, monkeypatch):
    destino = tmp_path / "novo.bin"
    monkeypatch.setattr(http, "fetch", lambda url, timeout=30: b"baixado")
    http.baixar_recurso("http://x", destino, logging.getLogger("t"))
    assert destino.read_bytes() == b"baixado"


def test_baixar_recurso_propaga_erro(tmp_path, monkeypatch):
    destino = tmp_path / "falha.bin"
    def _erro(*a, **k):
        raise OSError("rede caiu")
    monkeypatch.setattr(http, "fetch", _erro)
    with pytest.raises(OSError):
        http.baixar_recurso("http://x", destino, logging.getLogger("t"))
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grugeen_dashboards.comum.http'`.

- [ ] **Step 3: Implementar o mínimo para passar**

`grugeen_dashboards/comum/http.py`:

```python
"""Download de recursos com cache em disco e detecção automática de gzip."""

import gzip
import logging
import urllib.request
from pathlib import Path


def fetch(url: str, timeout: int = 30) -> bytes:
    """Baixa a URL e retorna bytes crus (descomprime gzip se necessário)."""
    req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def baixar_recurso(url: str, destino: Path, logger: logging.Logger) -> None:
    """Baixa `url` para `destino` se ainda não existir; loga e propaga erros."""
    destino = Path(destino)
    if destino.exists():
        logger.info("Cache: %s", destino.name)
        return
    logger.info("Baixando %s ...", destino.name)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        destino.write_bytes(fetch(url))
        logger.info("  %.1f KB", destino.stat().st_size / 1024)
    except Exception as exc:
        logger.error("Falha: %s — %s", destino.name, exc)
        raise
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_http.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar:

```python
from .http import fetch, baixar_recurso
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/http.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_http.py"
git commit -m "feat: comum.http — fetch/baixar_recurso com testes"
```

---

## Task 5: `logging_setup.py` — logging parametrizado

Origem: `mapa_consumo_mensal.py:149-165` e `mapa_prospecao_cnpjs.py:142-156`. Diferiam só
no prefixo do nome do arquivo (`mapa_consumo_` vs `mapa_prospecao_`) e no diretório.
Parametriza ambos.

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/comum/logging_setup.py`
- Test: `Mapas de Consumo/tests/test_logging_setup.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_logging_setup.py`:

```python
import logging
from grugeen_dashboards.comum.logging_setup import setup_logging


def test_setup_logging_cria_arquivo_com_prefixo(tmp_path):
    logger = setup_logging("teste_dash", tmp_path)
    logger.info("linha de teste")
    for h in logger.handlers:
        h.flush()
    arquivos = list(tmp_path.glob("teste_dash_*.log"))
    assert len(arquivos) == 1
    assert "linha de teste" in arquivos[0].read_text(encoding="utf-8")


def test_setup_logging_retorna_logger():
    logger = setup_logging("x", None)
    assert isinstance(logger, logging.Logger)
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_logging_setup.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar o mínimo para passar**

`grugeen_dashboards/comum/logging_setup.py`:

```python
"""Configuração de logging com arquivo por execução (timestamp) + stdout UTF-8."""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(prefixo: str, pasta_logs: Path | None) -> logging.Logger:
    """
    Configura logging em nível INFO. Se `pasta_logs` for informada, grava um
    arquivo `{prefixo}_{timestamp}.log` nela; sempre espelha em stdout (UTF-8).
    """
    handlers: list[logging.Handler] = []
    if pasta_logs is not None:
        pasta_logs = Path(pasta_logs)
        pasta_logs.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = pasta_logs / f"{prefixo}_{ts}.log"
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    # Garante saída UTF-8 no console (Windows usa cp1252 por padrão) reconfigurando
    # o stream no lugar — não cria um wrapper novo que fecharia o buffer (o que
    # quebraria a captura do pytest). Degrada graciosamente quando stdout não
    # suporta reconfigure (ex.: capturado em testes).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(prefixo)
```

> `force=True` evita que chamadas repetidas em testes acumulem handlers.
> Usamos `sys.stdout.reconfigure(...)` em vez de envolver `sys.stdout.buffer` num
> novo `TextIOWrapper`: o wrapper fecharia o buffer ao ser coletado/reconfigurado,
> quebrando a captura do pytest. A reconfiguração no lugar preserva o efeito
> (console UTF-8) e é segura nos testes.

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_logging_setup.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar:

```python
from .logging_setup import setup_logging
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/logging_setup.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_logging_setup.py"
git commit -m "feat: comum.logging_setup parametrizado com testes"
```

---

## Task 6: `marca.py` — logo como data URI

Origem: `mapa_consumo_mensal.py:138-144` (`_logo_data_uri`). Recebe o caminho do logo por
parâmetro em vez de constante global.

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/comum/marca.py`
- Test: `Mapas de Consumo/tests/test_marca.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_marca.py`:

```python
from grugeen_dashboards.comum.marca import logo_data_uri


def test_logo_inexistente_retorna_vazio(tmp_path):
    assert logo_data_uri(tmp_path / "nao_existe.png") == ""


def test_logo_existente_retorna_data_uri(tmp_path):
    png = tmp_path / "logo.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    uri = logo_data_uri(png)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > len("data:image/png;base64,")
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_marca.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar o mínimo para passar**

`grugeen_dashboards/comum/marca.py`:

```python
"""Recursos visuais da marca Grugeen (logo embutido)."""

import base64
from pathlib import Path


def logo_data_uri(logo_path: Path) -> str:
    """Retorna o logo PNG como data URI base64; string vazia se não existir."""
    try:
        data = base64.b64encode(Path(logo_path).read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    except Exception:
        return ""
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_marca.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar:

```python
from .marca import logo_data_uri
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/marca.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_marca.py"
git commit -m "feat: comum.marca.logo_data_uri com testes"
```

---

## Task 7: `energia.py` — gestão de energia do Windows

Origem: `mapa_consumo_mensal.py:1712-1728` (`_prevent_sleep`, `_restore_sleep`).
Idênticos nos dois scripts. Testável apenas no contrato "não levanta exceção".

**Files:**
- Create: `Mapas de Consumo/grugeen_dashboards/comum/energia.py`
- Test: `Mapas de Consumo/tests/test_energia.py`

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_energia.py`:

```python
from grugeen_dashboards.comum import energia


def test_prevent_sleep_nao_levanta():
    # Em qualquer plataforma: não deve propagar exceção.
    energia.prevent_sleep()


def test_restore_sleep_nao_levanta():
    energia.restore_sleep()
```

- [ ] **Step 2: Rodar o teste para confirmar a falha**

Run: `python -m pytest tests/test_energia.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar o mínimo para passar**

`grugeen_dashboards/comum/energia.py`:

```python
"""Impede a suspensão do Windows durante execuções longas (no-op fora do Windows)."""

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def prevent_sleep() -> None:
    """Impede que o Windows entre em espera/hibernação durante a execução."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        )
    except Exception:
        pass  # não-Windows ou sem permissão — ignora silenciosamente


def restore_sleep() -> None:
    """Restaura a gestão de energia normal do Windows."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass
```

> `import ctypes` é feito dentro da função para que `ctypes.windll` (que só existe no
> Windows) não quebre a importação do módulo em outras plataformas de CI.

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_energia.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Reexportar em `comum/__init__.py`**

Adicionar:

```python
from .energia import prevent_sleep, restore_sleep
```

- [ ] **Step 6: Commit**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/energia.py" "Mapas de Consumo/grugeen_dashboards/comum/__init__.py" "Mapas de Consumo/tests/test_energia.py"
git commit -m "feat: comum.energia prevent/restore_sleep com testes"
```

---

## Task 8: Suíte completa verde e API pública consolidada

**Files:**
- Verify: `Mapas de Consumo/grugeen_dashboards/comum/__init__.py`

- [ ] **Step 1: Conferir o `__init__.py` final do comum**

`grugeen_dashboards/comum/__init__.py` deve conter exatamente estes reexports:

```python
"""Funções auxiliares compartilhadas entre as seções do dashboard."""

from .formato import (
    formatar_br, fmt_gwh, fmt_mwh, fmt_mwh_hab, fmt_cons_100k, fmt_pop,
)
from .geo import normalizar, geocodificar
from .http import fetch, baixar_recurso
from .logging_setup import setup_logging
from .marca import logo_data_uri
from .energia import prevent_sleep, restore_sleep

__all__ = [
    "formatar_br", "fmt_gwh", "fmt_mwh", "fmt_mwh_hab", "fmt_cons_100k", "fmt_pop",
    "normalizar", "geocodificar",
    "fetch", "baixar_recurso",
    "setup_logging",
    "logo_data_uri",
    "prevent_sleep", "restore_sleep",
]
```

- [ ] **Step 2: Rodar a suíte completa**

Run: `python -m pytest`
Expected: PASS — 26 testes (8 formato + 7 geo + 5 http + 2 logging + 2 marca + 2 energia). Confirmar o total exibido e que não há falhas.

> Se o total divergir, conferir se algum teste foi pulado/omitido nas tasks anteriores.

- [ ] **Step 3: Smoke test de importação da API pública**

Run: `python -c "from grugeen_dashboards.comum import formatar_br, normalizar, geocodificar, fetch, baixar_recurso, setup_logging, logo_data_uri, prevent_sleep, restore_sleep; print('ok')"`
Expected: imprime `ok` sem erros.

- [ ] **Step 4: Commit final (se houver ajuste no `__init__.py`)**

```bash
git add "Mapas de Consumo/grugeen_dashboards/comum/__init__.py"
git commit -m "chore: consolidar API publica de grugeen_dashboards.comum"
```

---

## Self-Review (preenchido pelo autor do plano)

- **Cobertura da spec (Fase 1):** a spec lista em `comum/`: `http`, `geo`, `logging_setup`,
  `formato`, `energia`, `marca`. Todos cobertos (Tasks 1–7). Os `_ALIASES` ficam fora do
  comum por serem dataset-específicos (documentado na Task 2/3) — coerente com a spec, que
  fala em deduplicar funções, não dados.
- **Placeholders:** nenhum — todo passo traz o código/expected concretos.
- **Consistência de tipos/nomes:** API estável (`formatar_br`, `normalizar`,
  `geocodificar`, `fetch`, `baixar_recurso`, `setup_logging`, `logo_data_uri`,
  `prevent_sleep`, `restore_sleep`) usada de forma idêntica nos reexports e no smoke test.
- **Não-objetivo respeitado:** esta fase NÃO toca os monólitos; sem risco de regressão
  visual aqui.

---

## Roadmap dos próximos planos (a detalhar quando alcançados)

> Cada plano abaixo só é escrito ao ser iniciado, pois depende de interfaces travadas no
> plano anterior. Cada um termina com commit verde e software testável.

- **Plano 2 — Captura de baseline + camada de dados das seções.** Rodar os dashboards
  atuais e arquivar os HTMLs como referência (requer os arquivos de dados da CCEE/RF —
  passo manual do usuário). Extrair `consumo/dados.py` e `prospeccao/dados.py` (agregações
  puras) reaproveitando `comum/`, com testes sobre DataFrames pequenos.
- **Plano 3 — Contrato + gerador + 1ª seção (consumo).** Fixar o schema JSON do contrato a
  partir do que o dashboard de consumo produz; `geracao/gerador.py` com os dois modos de
  saída; `assets/` (CSS + `core/*.js`) com a barra de filtros geográficos. Comparar contra
  o baseline até paridade; então corrigir os bugs de hover/zoom/filtro com o JS testável.
- **Plano 4 — 2ª seção (prospecção) + drill-down cruzado.** Adicionar prospecção como
  seção ligada ao `filterState` compartilhado; habilitar clique-para-filtrar cruzado e
  sincronização mapa↔tabela.
- **Plano 5 — Novos filtros + aposentadoria dos monólitos.** Critérios adicionais,
  persistência na URL e exportação; remover `mapa_consumo_mensal.py`/`mapa_prospecao_cnpjs.py`;
  atualizar README.
```


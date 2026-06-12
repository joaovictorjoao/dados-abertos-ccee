# =============================================================================
# SCRIPT: Pico mensal de CONSUMO_CARGA_ACL por consumidor — base de 12 meses
# Fonte: CCEE - Dados Abertos - consumo_horario_perfil_agente
# =============================================================================
# OBJETIVO:
#   Consolidar, em UMA base no formato "exemplo_12m.csv", o PICO HORÁRIO de
#   CONSUMO_CARGA_ACL de cada consumidor (CODIGO_CARGA) mês a mês.
#   Cada linha = um consumidor; cada coluna mensal = maior valor de
#   CONSUMO_CARGA_ACL registrado em qualquer hora daquele mês.
#
# FORMATO DE SAÍDA (idêntico a bases/exemplo_12m.csv):
#   CODIGO_CARGA;NOME_CARGA;CNPJ_CARGA;CIDADE_CARGA;ESTADO_CARGA;SUBMERCADO;
#   SIGLA_PERFIL_AGENTE;CLASSE_PERFIL_AGENTE;SIGLA_PERFIL_AGENTE_DISTRIBUIDORA;
#   <um rótulo por mês: mai/25, jun/25, ...>
#   Separador ";", decimal ",", UTF-8 com BOM, quebras CRLF (abre direto no Excel pt-BR).
#
# REGRAS DE CONSOLIDAÇÃO (definidas com o usuário):
#   - Métrica por célula: PICO horário (MAX de CONSUMO_CARGA_ACL no mês).
#   - Dados cadastrais (nome/CNPJ/cidade/perfil...): do MÊS MAIS RECENTE em que
#     o consumidor aparece (mantém coerência com o cadastro atual).
#   - Meses: DESCOBERTOS automaticamente a partir dos arquivos presentes na
#     pasta (consumo_horario_perfil_agente_AAAAMM.csv.gz), em ordem cronológica.
#
# DADOS:
#   Arquivos CSV comprimidos (.csv.gz), separador ";", encoding latin-1.
#   ~34 milhões de linhas por mês. Não carregados em RAM — DuckDB lê do disco;
#   o fallback Python lê em fluxo (streaming).
#
# DESEMPENHO (SSD, 16 GB RAM):
#   DuckDB (instalado):           ~30–60 s por mês  →  ~6–12 min no total
#   Python puro (fallback):       ~2,5–3 min por mês →  ~30–40 min no total
#
# COMO USAR:
#   1. Garanta que os arquivos mensais completos estão nesta pasta.
#   2. (Opcional) pip install duckdb  — já detectado/usado automaticamente.
#   3. python consumo_pico_12m.py
# =============================================================================

import csv
import gzip
import io
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO — AJUSTAR AQUI (se necessário)
# ─────────────────────────────────────────────────────────────────────────────
PASTA = Path(__file__).parent
PADRAO_ENTRADA = "consumo_horario_perfil_agente_*.csv.gz"

PASTA_BASES = PASTA / "bases"
ARQUIVO_SAIDA = PASTA_BASES / "consumo_pico_12m.csv"
PASTA_LOGS = PASTA / "logs"

# Coluna cujo pico (máximo horário no mês) é extraído
COLUNA_CONSUMO = "CONSUMO_CARGA_ACL"

# Colunas cadastrais (identidade do consumidor), na ordem do exemplo_12m.csv
COLUNAS_ID = [
    "NOME_CARGA",
    "CNPJ_CARGA",
    "CIDADE_CARGA",
    "ESTADO_CARGA",
    "SUBMERCADO",
    "SIGLA_PERFIL_AGENTE",
    "CLASSE_PERFIL_AGENTE",
    "SIGLA_PERFIL_AGENTE_DISTRIBUIDORA",
]

# Colunas de texto que precisam de limpeza de caracteres de controle (C0/C1)
COLUNAS_TEXTO = {
    "NOME_CARGA", "CNPJ_CARGA", "CIDADE_CARGA", "ESTADO_CARGA",
    "SIGLA_PERFIL_AGENTE", "CLASSE_PERFIL_AGENTE",
    "SIGLA_PERFIL_AGENTE_DISTRIBUIDORA", "SUBMERCADO",
}

SEPARADOR = ";"
ENCODING = "latin-1"
PROGRESSO_A_CADA = 5_000_000  # linhas (fallback Python)

MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]
_RE_AAAAMM = re.compile(r"_(\d{6})\.csv\.gz$", re.IGNORECASE)
# ─────────────────────────────────────────────────────────────────────────────


def _limpar(valor: str) -> str:
    """Remove caracteres de controle (C0 e C1) preservando espaços normais."""
    if not isinstance(valor, str):
        return valor
    return "".join(c for c in valor if c.isprintable() or c == " ")


def _rotulo_mes(aaaamm: str) -> str:
    """'202505' -> 'mai/25' (formato do exemplo_12m.csv)."""
    mes = int(aaaamm[4:6])
    return f"{MESES_PT[mes - 1]}/{aaaamm[2:4]}"


def _setup_logging() -> logging.Logger:
    PASTA_LOGS.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = PASTA_LOGS / f"consumo_pico_12m_{ts}.log"
    fmt = "%(asctime)s | %(levelname)s | %(message)s"
    # Força UTF-8 no console do Windows para não corromper acentos
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


def _descobrir_arquivos(logger: logging.Logger) -> list[tuple[str, Path]]:
    """Lista (AAAAMM, caminho) para cada arquivo mensal, em ordem cronológica."""
    encontrados: list[tuple[str, Path]] = []
    for arq in PASTA.glob(PADRAO_ENTRADA):
        m = _RE_AAAAMM.search(arq.name)
        if m:
            encontrados.append((m.group(1), arq))
    encontrados.sort(key=lambda t: t[0])

    if not encontrados:
        raise FileNotFoundError(
            f"Nenhum arquivo '{PADRAO_ENTRADA}' encontrado em {PASTA}"
        )

    logger.info("Arquivos mensais encontrados: %d", len(encontrados))
    for aaaamm, arq in encontrados:
        tam_mb = arq.stat().st_size / 1024**2
        alerta = "  <-- ATENÇÃO: arquivo pequeno, pode estar incompleto" if tam_mb < 50 else ""
        logger.info("  %s (%s) | %.1f MB%s", _rotulo_mes(aaaamm), arq.name, tam_mb, alerta)
    return encontrados


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO POR MÊS — retorna { CODIGO_CARGA(str): {"pico": float, <COLUNAS_ID>} }
# ─────────────────────────────────────────────────────────────────────────────

def _pico_mes_duckdb(arquivo: Path, logger: logging.Logger) -> dict:
    """Pico por CODIGO_CARGA via DuckDB. Identidade tirada da linha do pico."""
    import duckdb  # type: ignore[import]

    arquivo_fwd = str(arquivo).replace("\\", "/")
    # arg_max(coluna, valor) = valor da coluna na linha de maior 'valor' (ignora NULLs)
    sel_id = ",\n            ".join(
        f"arg_max({c}, TRY_CAST({COLUNA_CONSUMO} AS DOUBLE)) AS {c}"
        for c in COLUNAS_ID
    )
    sql = f"""
    SELECT
        CODIGO_CARGA,
        MAX(TRY_CAST({COLUNA_CONSUMO} AS DOUBLE)) AS pico,
        {sel_id}
    FROM read_csv(
        '{arquivo_fwd}',
        delim='{SEPARADOR}',
        quote='"',
        header=true,
        ignore_errors=true,
        all_varchar=true
    )
    WHERE TRY_CAST({COLUNA_CONSUMO} AS DOUBLE) IS NOT NULL
    GROUP BY CODIGO_CARGA
    """
    df = duckdb.sql(sql).df()

    res: dict[str, dict] = {}
    for rec in df.to_dict("records"):
        cod = str(rec["CODIGO_CARGA"]).strip()
        info = {"pico": float(rec["pico"])}
        for c in COLUNAS_ID:
            v = rec.get(c)
            v = "" if v is None else str(v)
            info[c] = _limpar(v) if c in COLUNAS_TEXTO else v
        res[cod] = info
    return res


def _pico_mes_python(arquivo: Path, logger: logging.Logger) -> dict:
    """Pico por CODIGO_CARGA em fluxo (fallback sem DuckDB)."""
    peak: dict[str, dict] = {}
    linhas = erros = 0
    t0 = time.perf_counter()

    with gzip.open(arquivo, "rt", encoding=ENCODING) as f:
        reader = csv.DictReader(f, delimiter=SEPARADOR)
        cabecalho = set(reader.fieldnames or [])
        faltando = ({COLUNA_CONSUMO, "CODIGO_CARGA"} | set(COLUNAS_ID)) - cabecalho
        if faltando:
            raise ValueError(
                f"Colunas ausentes em {arquivo.name}: {faltando}. "
                f"Disponíveis: {sorted(cabecalho)}"
            )

        for row in reader:
            linhas += 1
            raw = row.get(COLUNA_CONSUMO, "")
            if raw:
                try:
                    consumo = float(raw)
                except ValueError:
                    erros += 1
                else:
                    cod = row["CODIGO_CARGA"]
                    atual = peak.get(cod)
                    if atual is None or consumo > atual["pico"]:
                        info = {"pico": consumo}
                        for c in COLUNAS_ID:
                            v = row.get(c, "")
                            info[c] = _limpar(v) if c in COLUNAS_TEXTO else v
                        peak[cod] = info
            else:
                erros += 1

            if linhas % PROGRESSO_A_CADA == 0:
                dec = time.perf_counter() - t0
                logger.info(
                    "    %10d linhas | %d cargas | %.1f s | %.0f linhas/s",
                    linhas, len(peak), dec, linhas / dec,
                )

    logger.info(
        "    Mês lido: %d linhas | %d cargas | %d erros | %.1f s",
        linhas, len(peak), erros, time.perf_counter() - t0,
    )
    return peak


# ─────────────────────────────────────────────────────────────────────────────
# CONSOLIDAÇÃO E GRAVAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def _consolidar(arquivos: list[tuple[str, Path]], extrair, logger: logging.Logger):
    """Funde os picos mensais. Cadastro = mês mais recente (iteração ascendente)."""
    valores: dict[str, dict[str, float]] = {}     # codigo -> {rotulo: pico}
    identidade: dict[str, dict[str, str]] = {}     # codigo -> dados cadastrais
    rotulos: list[str] = []

    for aaaamm, arquivo in arquivos:               # ordem cronológica crescente
        rotulo = _rotulo_mes(aaaamm)
        rotulos.append(rotulo)
        logger.info("Processando %s (%s)...", rotulo, arquivo.name)
        t0 = time.perf_counter()

        res = extrair(arquivo, logger)
        for cod, info in res.items():
            valores.setdefault(cod, {})[rotulo] = info["pico"]
            # Sobrescreve a cada mês → ao final fica o mês mais recente presente
            identidade[cod] = {c: info[c] for c in COLUNAS_ID}

        logger.info("  %s: %d cargas | %.1f s", rotulo, len(res), time.perf_counter() - t0)

    return valores, identidade, rotulos


def _gravar(valores, identidade, rotulos, logger: logging.Logger) -> None:
    import pandas as pd  # type: ignore[import]

    codigos = sorted(valores, key=lambda c: int(c) if c.lstrip("-").isdigit() else 0)

    linhas = []
    for cod in codigos:
        cod_out = int(cod) if cod.lstrip("-").isdigit() else cod
        linha = {"CODIGO_CARGA": cod_out, **identidade[cod]}
        for r in rotulos:
            linha[r] = valores[cod].get(r)  # ausente => None => célula vazia
        linhas.append(linha)

    colunas = ["CODIGO_CARGA"] + COLUNAS_ID + rotulos
    df = pd.DataFrame(linhas, columns=colunas)

    PASTA_BASES.mkdir(exist_ok=True)
    logger.info("Gravando: %s (%d consumidores, %d meses)",
                ARQUIVO_SAIDA.name, len(df), len(rotulos))
    t0 = time.perf_counter()
    # utf-8-sig (BOM) + decimal vírgula + CRLF → idêntico ao exemplo_12m.csv
    df.to_csv(
        ARQUIVO_SAIDA,
        sep=SEPARADOR,
        decimal=",",
        index=False,
        encoding="utf-8-sig",
        lineterminator="\r\n",
    )
    logger.info("Gravado em %.1f s", time.perf_counter() - t0)

    # --- Validação ---
    logger.info("--- VALIDAÇÃO ---")
    logger.info("Consumidores (linhas): %d", len(df))
    logger.info("Meses (colunas):       %d  [%s]", len(rotulos), ", ".join(rotulos))
    logger.info("CNPJ vazio:            %d", df["CNPJ_CARGA"].eq("").sum())
    for r in rotulos:
        serie = pd.to_numeric(df[r], errors="coerce")
        preenchidas = serie.notna().sum()
        logger.info(
            "  %-8s | preenchidas: %5d | min: %.2f | máx: %.2f",
            r, preenchidas,
            serie.min(skipna=True) if preenchidas else float("nan"),
            serie.max(skipna=True) if preenchidas else float("nan"),
        )


def main() -> None:
    logger = _setup_logging()
    logger.info("=" * 70)
    logger.info("INÍCIO: consumo_pico_12m — base de pico mensal por consumidor")

    arquivos = _descobrir_arquivos(logger)
    t_total = time.perf_counter()

    try:
        import duckdb
        duckdb.sql("PRAGMA disable_progress_bar")  # mantém logs limpos
        logger.info("DuckDB disponível — usando engine SQL nativo (rápido)")
        extrair = _pico_mes_duckdb
    except ImportError:
        logger.info("DuckDB não instalado — usando Python puro (mais lento)")
        logger.info("Para acelerar: pip install duckdb")
        extrair = _pico_mes_python

    valores, identidade, rotulos = _consolidar(arquivos, extrair, logger)
    _gravar(valores, identidade, rotulos, logger)

    logger.info("CONCLUÍDO em %.1f s", time.perf_counter() - t_total)
    logger.info("Resultado: %s", ARQUIVO_SAIDA)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

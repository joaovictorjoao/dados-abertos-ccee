# =============================================================================
# SCRIPT: Pico mensal de CONSUMO_CARGA_ACL por CODIGO_CARGA
# Fonte: CCEE - Dados Abertos - consumo_horario_perfil_agente
# =============================================================================
# OBJETIVO:
#   Para cada CODIGO_CARGA, identificar o período de pico (linha com maior
#   CONSUMO_CARGA_ACL no mês) e exportar para Excel.
#
# DADOS:
#   Arquivo CSV comprimido (.csv.gz), separador ";", encoding latin-1.
#   ~34 milhões de linhas por mês. Não é carregado em memória — lido em fluxo.
#
# DESEMPENHO MEDIDO (hardware de referência: SSD, 16 GB RAM, 8 núcleos):
#   Abordagem atual (Python puro, streaming):  ~2,5–3 min
#   Com DuckDB instalado (pip install duckdb):  ~30–60 s
#   Com Polars instalado (pip install polars):  ~45–90 s
#
# COMO USAR:
#   1. Ajustar ARQUIVO_ENTRADA e ARQUIVO_SAIDA abaixo.
#   2. (Opcional) pip install duckdb  — reduz tempo de 3 min para <1 min.
#   3. python consumo_pico_por_carga.py
# =============================================================================

import csv
import gzip
import io
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO — AJUSTAR AQUI
# ─────────────────────────────────────────────────────────────────────────────
ARQUIVO_ENTRADA = Path(
    r"C:\Grugeen\Grugeen Consultoria Ltda\Mercado Livre de Energia - Documentos"
    r"\1-PRINCIPAL\Arquivos de Medicao\Dados Abertos CCEE\Consumo Horário"
    r"\consumo_horario_perfil_agente_202604.csv.gz"
)

# Derivado automaticamente do nome do arquivo de entrada
_MES = ARQUIVO_ENTRADA.with_suffix("").with_suffix("").name.replace(
    "consumo_horario_perfil_agente_", ""
)
PASTA_BASES = ARQUIVO_ENTRADA.parent / "bases"
ARQUIVO_SAIDA = PASTA_BASES / f"consumo_pico_por_carga_{_MES}.xlsx"

# Pasta de logs (criada automaticamente)
PASTA_LOGS = ARQUIVO_ENTRADA.parent / "logs"

# Coluna de consumo a ser maximizada
COLUNA_CONSUMO = "CONSUMO_CARGA_ACL"

# Colunas a manter no resultado final (subset do CSV)
COLUNAS_SAIDA = [
    "MES_REFERENCIA",
    "CODIGO_CARGA",
    "NOME_CARGA",
    "CNPJ_CARGA",
    "CIDADE_CARGA",
    "ESTADO_CARGA",
    "SUBMERCADO",
    "SIGLA_PERFIL_AGENTE",
    "CLASSE_PERFIL_AGENTE",
    "SIGLA_PERFIL_AGENTE_DISTRIBUIDORA",
    "DATA",
    "PERIODO_COMERCIALIZACAO",
    "CONSUMO_CARGA_ACL",
    "CONSUMO_CARGA_AJUSTADO_ACL",
]

SEPARADOR = ";"
ENCODING = "latin-1"
PROGRESSO_A_CADA = 5_000_000  # linhas

# Colunas de texto que precisam de limpeza de caracteres de controle
COLUNAS_TEXTO = {
    "NOME_CARGA", "CNPJ_CARGA", "CIDADE_CARGA", "ESTADO_CARGA",
    "SIGLA_PERFIL_AGENTE", "CLASSE_PERFIL_AGENTE",
    "SIGLA_PERFIL_AGENTE_DISTRIBUIDORA", "SUBMERCADO",
}
# ─────────────────────────────────────────────────────────────────────────────


def _limpar(valor: str) -> str:
    """Remove caracteres de controle (C0 e C1) preservando espaços normais."""
    return "".join(c for c in valor if c.isprintable() or c == " ")


def _setup_logging() -> logging.Logger:
    PASTA_LOGS.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = PASTA_LOGS / f"consumo_pico_{ts}.log"
    fmt = "%(asctime)s | %(levelname)s | %(message)s"
    # Force UTF-8 on Windows console to avoid garbled accents
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


def _extrair_pico_python(logger: logging.Logger) -> dict:
    """Lê o CSV em fluxo e mantém, por CODIGO_CARGA, apenas a linha de pico."""
    peak: dict[str, tuple[float, dict]] = {}
    linhas_lidas = erros = 0

    logger.info("Iniciando leitura em fluxo: %s", ARQUIVO_ENTRADA.name)
    t0 = time.perf_counter()

    with gzip.open(ARQUIVO_ENTRADA, "rt", encoding=ENCODING) as f:
        reader = csv.DictReader(f, delimiter=SEPARADOR)

        # Valida cabeçalho antes de processar
        cabecalho = set(reader.fieldnames or [])
        faltando = set(COLUNAS_SAIDA) - cabecalho
        if faltando:
            raise ValueError(
                f"Colunas ausentes no arquivo: {faltando}. "
                f"Colunas disponíveis: {sorted(cabecalho)}"
            )

        for row in reader:
            linhas_lidas += 1
            raw = row.get(COLUNA_CONSUMO, "")
            if not raw:
                erros += 1
                continue
            try:
                consumo = float(raw)
            except ValueError:
                erros += 1
                continue

            cid = row["CODIGO_CARGA"]
            if cid not in peak or consumo > peak[cid][0]:
                peak[cid] = (consumo, {
                    k: (_limpar(row[k]) if k in COLUNAS_TEXTO else row[k])
                    for k in COLUNAS_SAIDA
                })

            if linhas_lidas % PROGRESSO_A_CADA == 0:
                decorrido = time.perf_counter() - t0
                taxa = linhas_lidas / decorrido
                logger.info(
                    "  %10d linhas | %d cargas | %.1f s | %.0f linhas/s",
                    linhas_lidas,
                    len(peak),
                    decorrido,
                    taxa,
                )

    decorrido = time.perf_counter() - t0
    logger.info(
        "Leitura concluída: %d linhas | %d cargas únicas | %d erros | %.1f s",
        linhas_lidas,
        len(peak),
        erros,
        decorrido,
    )
    return peak


def _extrair_pico_duckdb(logger: logging.Logger):
    """Extrai pico via DuckDB — requer: pip install duckdb pandas."""
    import duckdb  # type: ignore[import]
    import pandas as pd  # type: ignore[import]

    colunas_str = ", ".join(COLUNAS_SAIDA)
    logger.info("DuckDB disponível — usando engine SQL nativo")
    t0 = time.perf_counter()

    arquivo_fwd = str(ARQUIVO_ENTRADA).replace("\\", "/")
    sql = f"""
    SELECT {colunas_str}
    FROM (
        SELECT
            {colunas_str},
            ROW_NUMBER() OVER (
                PARTITION BY CODIGO_CARGA
                ORDER BY TRY_CAST({COLUNA_CONSUMO} AS DOUBLE) DESC NULLS LAST
            ) AS _rn
        FROM read_csv(
            '{arquivo_fwd}',
            delim='{SEPARADOR}',
            quote='"',
            header=true,
            ignore_errors=true,
            all_varchar=true
        )
    )
    WHERE _rn = 1
    ORDER BY TRY_CAST(CODIGO_CARGA AS INTEGER)
    """
    df = duckdb.sql(sql).df()

    # Apply same control-character stripping as the Python path
    for col in COLUNAS_TEXTO:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: _limpar(v) if isinstance(v, str) else v)

    logger.info("DuckDB concluído: %d cargas em %.1f s", len(df), time.perf_counter() - t0)
    return df


def _salvar_excel(dados, logger: logging.Logger) -> None:
    import pandas as pd  # type: ignore[import]

    if isinstance(dados, dict):
        registros = [row for _, row in dados.values()]
        df = pd.DataFrame(registros, columns=COLUNAS_SAIDA)
    else:
        df = dados.copy()

    # Garantir tipos numéricos independente do caminho (Python dict ou DuckDB all_varchar)
    for col in ("CODIGO_CARGA", "CONSUMO_CARGA_ACL", "CONSUMO_CARGA_AJUSTADO_ACL",
                "PERIODO_COMERCIALIZACAO", "CAPACIDADE_CARGA"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("CODIGO_CARGA").reset_index(drop=True)

    logger.info("Gravando Excel: %s (%d linhas)", ARQUIVO_SAIDA.name, len(df))
    t0 = time.perf_counter()
    df.to_excel(ARQUIVO_SAIDA, index=False, engine="openpyxl")
    logger.info("Excel gravado em %.1f s", time.perf_counter() - t0)

    # Sumário de validação
    logger.info("--- VALIDAÇÃO ---")
    logger.info("Linhas no resultado:  %d", len(df))
    logger.info("Cargas com CNPJ vazio: %d", df["CNPJ_CARGA"].eq("").sum())
    logger.info(
        "CONSUMO_CARGA_ACL — min: %.2f | max: %.2f | média: %.2f",
        df["CONSUMO_CARGA_ACL"].min(),
        df["CONSUMO_CARGA_ACL"].max(),
        df["CONSUMO_CARGA_ACL"].mean(),
    )


def main() -> None:
    logger = _setup_logging()
    logger.info("=" * 60)
    logger.info("INÍCIO: consumo_pico_por_carga")
    logger.info("Arquivo: %s (%.1f MB)", ARQUIVO_ENTRADA.name,
                ARQUIVO_ENTRADA.stat().st_size / 1024**2)

    if not ARQUIVO_ENTRADA.exists():
        logger.error("Arquivo não encontrado: %s", ARQUIVO_ENTRADA)
        raise FileNotFoundError(ARQUIVO_ENTRADA)

    PASTA_BASES.mkdir(exist_ok=True)
    t_total = time.perf_counter()

    # Tenta DuckDB primeiro (mais rápido); senão usa Python puro
    try:
        import duckdb  # noqa: F401
        dados = _extrair_pico_duckdb(logger)
    except ImportError:
        logger.info("DuckDB não instalado — usando Python puro (~2,5 min)")
        logger.info("Para acelerar: pip install duckdb")
        dados = _extrair_pico_python(logger)

    _salvar_excel(dados, logger)

    logger.info("CONCLUÍDO em %.1f s", time.perf_counter() - t_total)
    logger.info("Resultado: %s", ARQUIVO_SAIDA)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

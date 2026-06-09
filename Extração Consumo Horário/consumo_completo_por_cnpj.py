# =============================================================================
# SCRIPT: Medição horária completa de um CNPJ
# Fonte: CCEE - Dados Abertos - consumo_horario_perfil_agente
# =============================================================================
# OBJETIVO:
#   Extrair todas as linhas horárias de um CNPJ específico e exportar para CSV.
#   Útil para análise de perfil de carga, faturamento e auditorias.
#
# DADOS:
#   Arquivo CSV comprimido (.csv.gz), separador ";", encoding latin-1.
#   ~34 milhões de linhas por mês. Leitura em fluxo — não carrega tudo em RAM.
#
# DESEMPENHO MEDIDO (SSD, 16 GB RAM):
#   Python puro (streaming): ~2,5–3 min para varrer o arquivo completo
#   Com DuckDB (pip install duckdb): ~10–15 s
#
# COMO USAR:
#   1. Ajustar CNPJ_ALVO, ARQUIVO_ENTRADA e PASTA_SAIDA abaixo.
#   2. (Opcional) pip install duckdb
#   3. python consumo_completo_por_cnpj.py
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

# Ajuste o nome do arquivo conforme o mês desejado (AAAAMM)
ARQUIVO_ENTRADA = Path(__file__).parent / "consumo_horario_perfil_agente_202604.csv.gz"

# Pasta onde o CSV de saída será salvo (criada automaticamente)
PASTA_SAIDA = ARQUIVO_ENTRADA.parent / "bases"

SEPARADOR = ";"
ENCODING = "latin-1"
PROGRESSO_A_CADA = 5_000_000  # linhas

# ─────────────────────────────────────────────────────────────────────────────


def _somente_digitos(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


def _nome_saida(cnpj_digits: str) -> Path:
    # .with_suffix("").with_suffix("") remove .gz e .csv, deixando só o nome base
    mes = ARQUIVO_ENTRADA.with_suffix("").with_suffix("").name.replace(
        "consumo_horario_perfil_agente_", ""
    )
    PASTA_SAIDA.mkdir(exist_ok=True)
    return PASTA_SAIDA / f"medicao_cnpj_{cnpj_digits}_{mes}.csv"


def _setup_logging(cnpj_digits: str) -> logging.Logger:
    pasta_logs = ARQUIVO_ENTRADA.parent / "logs"
    pasta_logs.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = pasta_logs / f"cnpj_{cnpj_digits}_{ts}.log"
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


def _limpar(valor: str) -> str:
    """Remove caracteres de controle (C0/C1) presentes em alguns campos CCEE."""
    return "".join(c for c in valor if c.isprintable() or c == " ")


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO — DuckDB (rápido)
# ─────────────────────────────────────────────────────────────────────────────

def _extrair_duckdb(cnpj_digits: str, arquivo_saida: Path, logger: logging.Logger) -> int:
    import duckdb

    arquivo_fwd = str(ARQUIVO_ENTRADA).replace("\\", "/")
    arquivo_saida_fwd = str(arquivo_saida).replace("\\", "/")

    logger.info("DuckDB disponível — usando engine SQL nativo")
    t0 = time.perf_counter()

    sql = f"""
    COPY (
        SELECT *
        FROM read_csv(
            '{arquivo_fwd}',
            delim='{SEPARADOR}',
            quote='"',
            header=true,
            ignore_errors=true,
            all_varchar=true
        )
        WHERE regexp_replace(CNPJ_CARGA, '[^0-9]', '', 'g') = '{cnpj_digits}'
        ORDER BY DATA, TRY_CAST(PERIODO_COMERCIALIZACAO AS INTEGER)
    )
    TO '{arquivo_saida_fwd}'
    (HEADER true, DELIMITER ';')
    """
    duckdb.sql(sql)

    # Contar linhas no arquivo gerado (excluindo cabeçalho)
    with open(arquivo_saida, encoding="utf-8") as f:
        total = sum(1 for _ in f) - 1

    logger.info(
        "DuckDB concluído: %d linhas extraídas em %.1f s",
        total,
        time.perf_counter() - t0,
    )
    return total


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO — Python puro (fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _extrair_python(cnpj_digits: str, arquivo_saida: Path, logger: logging.Logger) -> int:
    logger.info("DuckDB não instalado — usando Python puro (~2,5–3 min)")
    logger.info("Para acelerar: pip install duckdb")

    t0 = time.perf_counter()
    linhas_lidas = linhas_gravadas = 0

    with (
        gzip.open(ARQUIVO_ENTRADA, "rt", encoding=ENCODING) as f_in,
        open(arquivo_saida, "w", newline="", encoding="utf-8") as f_out,
    ):
        reader = csv.DictReader(f_in, delimiter=SEPARADOR)

        if "CNPJ_CARGA" not in (reader.fieldnames or []):
            raise ValueError(
                f"Coluna CNPJ_CARGA não encontrada. "
                f"Colunas disponíveis: {reader.fieldnames}"
            )

        writer = csv.DictWriter(
            f_out,
            fieldnames=reader.fieldnames,
            delimiter=SEPARADOR,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in reader:
            linhas_lidas += 1
            if _somente_digitos(row.get("CNPJ_CARGA", "")) == cnpj_digits:
                # Limpa caracteres de controle nos campos de texto
                row_limpo = {
                    k: (_limpar(v) if isinstance(v, str) and not v.replace(".", "").replace("-", "").isdigit() else v)
                    for k, v in row.items()
                }
                writer.writerow(row_limpo)
                linhas_gravadas += 1

            if linhas_lidas % PROGRESSO_A_CADA == 0:
                decorrido = time.perf_counter() - t0
                logger.info(
                    "  %10d linhas lidas | %d encontradas | %.1f s | %.0f linhas/s",
                    linhas_lidas,
                    linhas_gravadas,
                    decorrido,
                    linhas_lidas / decorrido,
                )

    logger.info(
        "Concluído: %d linhas lidas | %d linhas do CNPJ | %.1f s",
        linhas_lidas,
        linhas_gravadas,
        time.perf_counter() - t0,
    )
    return linhas_gravadas


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSÃO PARA EXCEL (decimal vírgula + BOM UTF-8)
# ─────────────────────────────────────────────────────────────────────────────

def _adaptar_para_excel(arquivo_saida: Path, logger: logging.Logger) -> None:
    """
    Relê o CSV gerado (decimal '.') e o reescreve com decimal ',' e BOM UTF-8.
    Com isso o Excel em pt-BR abre diretamente sem distorcer os números.
    """
    import pandas as pd

    df = pd.read_csv(arquivo_saida, sep=SEPARADOR, decimal=".", encoding="utf-8")

    # Colunas que devem ser numéricas (escrita com vírgula decimal)
    colunas_numericas = [
        "CAPACIDADE_CARGA",
        "CONSUMO_CARGA_ACL",
        "CONSUMO_CARGA_AJUSTADO_ACL",
        "CONSUMO_CARGA_AJUSTADO",
        "CONSUMO_CARGA_PONTO_CONEXAO",
    ]
    for col in colunas_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # utf-8-sig = UTF-8 com BOM → Excel reconhece o encoding automaticamente
    df.to_csv(arquivo_saida, sep=SEPARADOR, decimal=",", index=False, encoding="utf-8-sig")
    logger.info("CSV adaptado para Excel (decimal vírgula, BOM UTF-8)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def _ler_cnpj() -> str:
    """Lê o CNPJ da linha de comando ou, se ausente, solicita interativamente."""
    import sys
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    print("=" * 60)
    print("  Extração de medição horária por CNPJ — CCEE Dados Abertos")
    print("=" * 60)
    return input("  Digite o CNPJ (com ou sem formatação): ").strip()


def main() -> None:
    cnpj_raw = _ler_cnpj()
    cnpj_digits = _somente_digitos(cnpj_raw)
    if len(cnpj_digits) != 14:
        raise ValueError(f"CNPJ inválido: '{cnpj_raw}' → {len(cnpj_digits)} dígitos (esperado: 14)")

    logger = _setup_logging(cnpj_digits)
    arquivo_saida = _nome_saida(cnpj_digits)

    logger.info("=" * 60)
    logger.info("CNPJ alvo:  %s", cnpj_digits)
    logger.info("Arquivo:    %s (%.1f MB)", ARQUIVO_ENTRADA.name, ARQUIVO_ENTRADA.stat().st_size / 1024**2)
    logger.info("Saída:      %s", arquivo_saida.name)

    if not ARQUIVO_ENTRADA.exists():
        logger.error("Arquivo de entrada não encontrado: %s", ARQUIVO_ENTRADA)
        raise FileNotFoundError(ARQUIVO_ENTRADA)

    t_total = time.perf_counter()

    try:
        import duckdb  # noqa: F401
        total = _extrair_duckdb(cnpj_digits, arquivo_saida, logger)
    except ImportError:
        total = _extrair_python(cnpj_digits, arquivo_saida, logger)

    if total == 0:
        logger.warning("Nenhuma linha encontrada para o CNPJ %s — verifique o valor informado.", cnpj_digits)
    else:
        _adaptar_para_excel(arquivo_saida, logger)
        tamanho_kb = arquivo_saida.stat().st_size / 1024
        logger.info("--- RESULTADO ---")
        logger.info("Linhas extraídas:  %d", total)
        logger.info("Tamanho do CSV:    %.1f KB", tamanho_kb)
        logger.info("Arquivo gerado:    %s", arquivo_saida)

    logger.info("CONCLUÍDO em %.1f s", time.perf_counter() - t_total)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

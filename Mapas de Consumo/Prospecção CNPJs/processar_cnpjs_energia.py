"""
Processador de Base CNPJs - Prospecção Mercado Livre de Energia
Receita Federal -> filtrar empresas com alto potencial de consumo energético

Fluxo:
  1. Extrai Base_CNPJs.7z → ZIPs de Estabelecimentos
  2. Processa cada ZIP em chunks (sem carregar tudo na memória)
  3. Filtra CNAEs de alto consumo + situação ATIVA
  4. Baixa/usa tabela MUNICIPIOS da RF para mapear códigos → nomes
  5. Cruza com participantes CCEE (se disponível)
  6. Gera dataset filtrado (parquet + CSV resumo)
"""

import os
import sys
import csv
import json
import time
import logging
import zipfile
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# CAMINHOS
# ─────────────────────────────────────────────────────────────────────────────

BASE_PROJETO     = Path(__file__).parent

# Coloque Base_CNPJs.7z nesta pasta antes de executar, ou ajuste o caminho abaixo
ARQUIVO_7Z       = BASE_PROJETO / "Base_CNPJs.7z"
DIR_EXTRACAO     = BASE_PROJETO / "Base CNPJs"

# Localização do 7-Zip — ajuste se necessário
import shutil as _shutil
_7Z_CANDIDATOS = [Path(r"C:\Program Files\7-Zip\7z.exe"), Path(r"C:\Program Files (x86)\7-Zip\7z.exe")]
SETE_ZIP_EXE     = Path(_shutil.which("7z") or next((p for p in _7Z_CANDIDATOS if p.exists()), _7Z_CANDIDATOS[0]))
DIR_BASES        = BASE_PROJETO / "bases"
DIR_RESULTADOS   = BASE_PROJETO / "resultados"
DIR_LOGS         = BASE_PROJETO / "logs"

ARQUIVO_LOG      = DIR_LOGS / f"processamento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
SAIDA_PARQUET    = DIR_RESULTADOS / "estabelecimentos_energia.parquet"
SAIDA_RESUMO     = DIR_RESULTADOS / "resumo_por_municipio_cnae.csv"
SAIDA_MUNICIPIOS = DIR_BASES / "municipios_rf.csv"

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ESTRUTURA DO ARQUIVO ESTABELECIMENTOS (RF - sem cabeçalho, sep=";")
# ─────────────────────────────────────────────────────────────────────────────

COLUNAS_ESTAB = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
    "nome_fantasia", "situacao_cadastral", "data_situacao_cadastral",
    "motivo_situacao_cadastral", "nome_cidade_exterior", "pais",
    "data_inicio_atividade", "cnae_fiscal_principal", "cnae_fiscal_secundaria",
    "tipo_logradouro", "logradouro", "numero", "complemento", "bairro",
    "cep", "uf", "municipio", "ddd_1", "telefone_1", "ddd_2", "telefone_2",
    "ddd_fax", "fax", "correio_eletronico", "situacao_especial",
    "data_situacao_especial",
]

COLUNAS_MANTER = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
    "nome_fantasia", "situacao_cadastral", "data_inicio_atividade",
    "cnae_fiscal_principal", "uf", "municipio",
]

COLUNAS_IDX = {c: i for i, c in enumerate(COLUNAS_ESTAB)}

# ─────────────────────────────────────────────────────────────────────────────
# FILTROS CNAE - SETORES DE ALTO CONSUMO ENERGÉTICO
# ─────────────────────────────────────────────────────────────────────────────
# Baseado em dados de consumo médio por setor (ANEEL/EPE)
# Tier 1 = consumo muito alto | Tier 2 = consumo alto | Tier 3 = consumo moderado

CNAE_SETORES = {
    # Seção B - Indústrias Extrativas
    "05": ("Extração de carvão mineral", 1),
    "06": ("Extração de petróleo e gás", 1),
    "07": ("Extração de minerais metálicos", 1),
    "08": ("Extração de minerais não-metálicos", 1),
    "09": ("Serviços de apoio à extração", 2),
    # Seção C - Indústria de Transformação
    "10": ("Fabricação de alimentos", 1),
    "11": ("Fabricação de bebidas", 1),
    "12": ("Fabricação de produtos do fumo", 2),
    "13": ("Fabricação de produtos têxteis", 1),
    "14": ("Confecção de artigos do vestuário", 2),
    "15": ("Curtimento e artefatos de couro", 2),
    "16": ("Fabricação de produtos de madeira", 1),
    "17": ("Fabricação de celulose e papel", 1),
    "18": ("Impressão e reprodução", 2),
    "19": ("Fabricação de coque e biocombustíveis", 1),
    "20": ("Fabricação de produtos químicos", 1),
    "21": ("Fabricação de farmoquímicos", 1),
    "22": ("Fabricação de borracha e plástico", 1),
    "23": ("Fabricação de minerais não-metálicos", 1),
    "24": ("Metalurgia", 1),
    "25": ("Fabricação de produtos de metal", 1),
    "26": ("Fabricação de equipamentos eletrônicos", 2),
    "27": ("Fabricação de máquinas e equipamentos elétricos", 1),
    "28": ("Fabricação de máquinas e equipamentos", 1),
    "29": ("Fabricação de veículos automotores", 1),
    "30": ("Fabricação de outros equipamentos de transporte", 1),
    "31": ("Fabricação de móveis", 2),
    "32": ("Fabricação de produtos diversos", 2),
    "33": ("Manutenção e reparação de máquinas", 2),
    # Seção D - Eletricidade e Gás
    "35": ("Eletricidade, gás, vapor e ar condicionado", 1),
    # Seção E - Água e Saneamento
    "36": ("Captação, tratamento e distribuição de água", 1),
    "37": ("Esgoto e atividades relacionadas", 2),
    "38": ("Coleta, tratamento e disposição de resíduos", 2),
    "39": ("Descontaminação e serviços de gestão de resíduos", 2),
    # Seção F - Construção
    "41": ("Construção de edifícios", 2),
    "42": ("Obras de infraestrutura", 2),
    "43": ("Serviços especializados de construção", 2),
    # Seção G - Comércio
    "46": ("Comércio por atacado", 2),
    "47": ("Comércio varejista", 3),
    # Seção H - Transporte e Armazenagem
    "49": ("Transporte terrestre", 2),
    "50": ("Transporte aquaviário", 2),
    "51": ("Transporte aéreo", 1),
    "52": ("Armazenagem e atividades auxiliares de transporte", 2),
    # Seção I - Alojamento e Alimentação
    "55": ("Alojamento", 2),
    # Seção J - Informação e Comunicação
    "61": ("Telecomunicações", 1),
    "62": ("Atividades dos serviços de TI", 3),
    "63": ("Tratamento de dados e hospedagem", 1),
    # Seção Q - Saúde Humana e Serviços Sociais
    "86": ("Atividades de atenção à saúde humana", 2),
    # Seção P - Educação
    "85": ("Educação", 3),
    # Seção R - Cultura, Esporte e Lazer
    "93": ("Atividades esportivas e de recreação", 3),
}

CNAE_PREFIXOS_VALIDOS = set(CNAE_SETORES.keys())

# ─────────────────────────────────────────────────────────────────────────────
# SITUAÇÃO CADASTRAL
# ─────────────────────────────────────────────────────────────────────────────

SITUACAO_ATIVA = "02"

# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────

def extrair_7z() -> list[Path]:
    """Extrai o arquivo 7z e retorna lista de ZIPs extraídos."""
    if not ARQUIVO_7Z.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {ARQUIVO_7Z}")

    zips_existentes = sorted(DIR_EXTRACAO.glob("Estabelecimentos*.zip"))
    if len(zips_existentes) == 10:
        log.info("ZIPs já extraídos (%d arquivos). Pulando extração.", len(zips_existentes))
        return zips_existentes

    log.info("Extraindo %s → %s (%.1f GB comprimido)...",
             ARQUIVO_7Z.name, DIR_EXTRACAO,
             ARQUIVO_7Z.stat().st_size / 1e9)

    DIR_EXTRACAO.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    resultado = subprocess.run(
        [str(SETE_ZIP_EXE), "x", str(ARQUIVO_7Z), f"-o{DIR_EXTRACAO}", "-y"],
        capture_output=True, text=True
    )

    if resultado.returncode != 0:
        log.error("Erro na extração:\n%s", resultado.stderr)
        raise RuntimeError("Falha ao extrair 7z")

    elapsed = time.time() - t0
    zips = sorted(DIR_EXTRACAO.glob("Estabelecimentos*.zip"))
    log.info("Extração concluída em %.1fs. %d ZIPs encontrados.", elapsed, len(zips))
    return zips


def _cnae_valido(cnae_str: str) -> bool:
    """Verifica se o CNAE (string de 7 dígitos) pertence a setor de alto consumo."""
    if not cnae_str or len(cnae_str) < 2:
        return False
    return cnae_str[:2] in CNAE_PREFIXOS_VALIDOS


def processar_zip(arquivo_zip: Path, chunk_size: int = 300_000) -> pd.DataFrame:
    """Lê CSV dentro do ZIP em chunks, filtra e retorna DataFrame filtrado."""
    log.info("Processando %s...", arquivo_zip.name)
    t0 = time.time()
    partes = []
    total_linhas = 0
    total_aceitas = 0

    with zipfile.ZipFile(arquivo_zip, "r") as zf:
        # RF usa nomes como "K3241.K03200Y0.D60509.ESTABELE" (sem extensão .csv)
        arquivos = zf.namelist()
        if not arquivos:
            log.warning("ZIP vazio: %s", arquivo_zip.name)
            return pd.DataFrame(columns=COLUNAS_MANTER)
        csv_name = arquivos[0]
        log.info("  Arquivo interno: %s", csv_name)

        with zf.open(csv_name) as f:
            reader = pd.read_csv(
                f,
                sep=";",
                header=None,
                names=COLUNAS_ESTAB,
                dtype=str,
                encoding="latin-1",
                chunksize=chunk_size,
                on_bad_lines="skip",
                low_memory=False,
            )
            for i, chunk in enumerate(reader):
                total_linhas += len(chunk)

                # Filtro 1: situação cadastral ATIVA
                mask_ativa = chunk["situacao_cadastral"] == SITUACAO_ATIVA

                # Filtro 2: CNAE de alto consumo
                cnae = chunk["cnae_fiscal_principal"].fillna("")
                mask_cnae = cnae.str[:2].isin(CNAE_PREFIXOS_VALIDOS)

                filtrado = chunk.loc[mask_ativa & mask_cnae, COLUNAS_MANTER].copy()
                total_aceitas += len(filtrado)
                partes.append(filtrado)

                if (i + 1) % 5 == 0:
                    log.info("  Chunk %d: %d linhas totais, %d aceitas até agora...",
                             i + 1, total_linhas, total_aceitas)

    elapsed = time.time() - t0
    resultado = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUNAS_MANTER)
    log.info("  Concluído: %d/%d linhas aceitas (%.1f%%) em %.1fs",
             total_aceitas, total_linhas,
             100 * total_aceitas / max(total_linhas, 1),
             elapsed)
    return resultado


def baixar_municipios_rf() -> pd.DataFrame | None:
    """
    Tenta baixar a tabela de Municípios da RF CNPJ.
    Retorna DataFrame com colunas [codigo, nome] ou None se falhar.
    """
    url = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2024-12/Municipios.zip"
    dest = DIR_BASES / "Municipios_RF.zip"

    if SAIDA_MUNICIPIOS.exists():
        log.info("Tabela de municípios RF já disponível: %s", SAIDA_MUNICIPIOS)
        return pd.read_csv(SAIDA_MUNICIPIOS, sep=";", dtype=str, encoding="latin-1",
                           header=None, names=["codigo", "nome"])

    log.info("Baixando tabela de municípios RF...")
    try:
        urllib.request.urlretrieve(url, dest)
        with zipfile.ZipFile(dest, "r") as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                df = pd.read_csv(f, sep=";", dtype=str, encoding="latin-1",
                                 header=None, names=["codigo", "nome"])
        df.to_csv(SAIDA_MUNICIPIOS, index=False, sep=";", encoding="utf-8-sig")
        log.info("Municípios RF salvos: %d registros", len(df))
        return df
    except Exception as e:
        log.warning("Não foi possível baixar Municípios RF: %s. Prosseguindo sem mapeamento.", e)
        return None


def enriquecer_com_municipios(df: pd.DataFrame, df_mun: pd.DataFrame | None) -> pd.DataFrame:
    """Adiciona coluna nome_municipio ao DataFrame principal."""
    if df_mun is None:
        df["nome_municipio"] = df["municipio"]
        return df
    df_mun = df_mun.rename(columns={"codigo": "municipio", "nome": "nome_municipio"})
    df_mun["municipio"] = df_mun["municipio"].str.strip().str.zfill(4)
    df["municipio"] = df["municipio"].str.strip().str.zfill(4)
    return df.merge(df_mun, on="municipio", how="left")


def adicionar_cnae_descricao(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas de descrição e tier do CNAE."""
    df["cnae_divisao"] = df["cnae_fiscal_principal"].fillna("").str[:2]
    df["cnae_descricao"] = df["cnae_divisao"].map(
        {k: v[0] for k, v in CNAE_SETORES.items()}
    )
    df["cnae_tier"] = df["cnae_divisao"].map(
        {k: v[1] for k, v in CNAE_SETORES.items()}
    ).fillna(3).astype(int)
    return df


def montar_cnpj_completo(df: pd.DataFrame) -> pd.DataFrame:
    """Monta o CNPJ de 14 dígitos como string."""
    df["cnpj"] = (
        df["cnpj_basico"].str.strip().str.zfill(8) +
        df["cnpj_ordem"].str.strip().str.zfill(4) +
        df["cnpj_dv"].str.strip().str.zfill(2)
    )
    return df


def gerar_resumo(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo por município + UF + CNAE divisão."""
    resumo = (
        df.groupby(["uf", "municipio", "nome_municipio", "cnae_divisao", "cnae_descricao", "cnae_tier"], dropna=False)
        .agg(
            total_empresas=("cnpj", "count"),
            matrizes=("identificador_matriz_filial", lambda x: (x == "1").sum()),
            filiais=("identificador_matriz_filial", lambda x: (x == "2").sum()),
        )
        .reset_index()
        .sort_values(["cnae_tier", "total_empresas"], ascending=[True, False])
    )
    return resumo


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 70)
    log.info("PROCESSADOR DE CNPJs - MERCADO LIVRE DE ENERGIA")
    log.info("Início: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 70)

    t_total = time.time()

    # 1. Extrair 7z
    zips = extrair_7z()

    # 2. Baixar tabela de municípios RF
    df_municipios = baixar_municipios_rf()

    # 3. Verificar se saída já existe (retomar de onde parou)
    partes_salvas = sorted(DIR_BASES.glob("parte_*.parquet"))
    zips_processados = {p.stem.split("_")[1] for p in partes_salvas}
    log.info("Partes já processadas: %s", sorted(zips_processados))

    # 4. Processar cada ZIP
    for arquivo_zip in zips:
        nome_base = arquivo_zip.stem  # ex: Estabelecimentos0
        if nome_base in zips_processados:
            log.info("Pulando %s (já processado).", nome_base)
            continue

        df_parte = processar_zip(arquivo_zip)
        df_parte = montar_cnpj_completo(df_parte)
        df_parte = adicionar_cnae_descricao(df_parte)

        saida_parte = DIR_BASES / f"parte_{nome_base}.parquet"
        df_parte.to_parquet(saida_parte, index=False)
        log.info("Parte salva: %s (%d registros)", saida_parte.name, len(df_parte))

    # 5. Consolidar todas as partes
    log.info("Consolidando partes...")
    partes_salvas = sorted(DIR_BASES.glob("parte_*.parquet"))
    if not partes_salvas:
        log.error("Nenhuma parte encontrada para consolidar.")
        return

    df_total = pd.concat([pd.read_parquet(p) for p in partes_salvas], ignore_index=True)
    log.info("Total consolidado: %d registros", len(df_total))

    # 6. Enriquecer com nomes de municípios
    df_total = enriquecer_com_municipios(df_total, df_municipios)

    # 7. Salvar dataset completo filtrado
    df_total.to_parquet(SAIDA_PARQUET, index=False)
    log.info("Dataset completo salvo: %s", SAIDA_PARQUET)

    # 8. Gerar resumo por município + CNAE
    df_resumo = gerar_resumo(df_total)
    df_resumo.to_csv(SAIDA_RESUMO, index=False, encoding="utf-8-sig", sep=";")
    log.info("Resumo salvo: %s (%d linhas)", SAIDA_RESUMO.name, len(df_resumo))

    # 9. Estatísticas finais
    elapsed = time.time() - t_total
    log.info("=" * 70)
    log.info("PROCESSAMENTO CONCLUÍDO em %.1f minutos", elapsed / 60)
    log.info("Total de empresas filtradas:  %d", len(df_total))
    log.info("Estados cobertos:             %d", df_total["uf"].nunique())
    log.info("Municípios cobertos:          %d", df_total["municipio"].nunique())
    log.info("CNAEs únicos:                 %d", df_total["cnae_divisao"].nunique())
    log.info("  Tier 1 (muito alto):        %d", (df_total["cnae_tier"] == 1).sum())
    log.info("  Tier 2 (alto):              %d", (df_total["cnae_tier"] == 2).sum())
    log.info("  Tier 3 (moderado):          %d", (df_total["cnae_tier"] == 3).sum())
    log.info("=" * 70)

    # 10. Quick report - Top 20 municípios por tier 1
    top_mun = (
        df_total[df_total["cnae_tier"] == 1]
        .groupby(["uf", "nome_municipio"])["cnpj"].count()
        .reset_index()
        .rename(columns={"cnpj": "empresas_tier1"})
        .sort_values("empresas_tier1", ascending=False)
        .head(20)
    )
    log.info("\nTop 20 municípios por empresas industriais (Tier 1):\n%s", top_mun.to_string(index=False))


if __name__ == "__main__":
    main()

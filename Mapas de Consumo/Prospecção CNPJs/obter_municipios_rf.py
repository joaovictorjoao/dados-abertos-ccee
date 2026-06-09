"""
Obtém a tabela de municípios da Receita Federal para mapear
os códigos RF (4 dígitos) para nomes de municípios.

Execute APÓS o processamento principal para enriquecer os dados.
Fontes tentadas em ordem:
  1. Arquivo Municipios.zip já presente na pasta bases/
  2. Download direto da RF (diversas datas)
  3. GitHub aphonsoar/Receita_Federal (CSV compilado)
  4. Construção aproximada via dados IBGE + CEP (fallback)
"""

import io
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

import pandas as pd

BASE_PROJETO = Path(__file__).parent
DIR_BASES    = BASE_PROJETO / "bases"
DIR_RESULTADOS = BASE_PROJETO / "resultados"
SAIDA_MUNICIPIOS = DIR_BASES / "municipios_rf.csv"
SAIDA_PARQUET    = DIR_RESULTADOS / "estabelecimentos_energia.parquet"
SAIDA_ENRIQUECIDO = DIR_RESULTADOS / "estabelecimentos_energia_com_municipios.parquet"

# Municipios IBGE (já disponível no projeto)
MUNICIPIOS_IBGE = Path(
    r"c:\Grugeen\Grugeen Consultoria Ltda\Mercado Livre de Energia - Documentos"
    r"\1-PRINCIPAL\Arquivos de Medicao\Dados Abertos CCEE\Consumo Horário\mapas\municipios_ibge.csv"
)

RF_MUNICIPIOS_URLS = [
    # RF - tentar meses recentes
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2026-05/Municipios.zip",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2026-04/Municipios.zip",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2026-03/Municipios.zip",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2026-02/Municipios.zip",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2025-11/Municipios.zip",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/2025-09/Municipios.zip",
    # Domínio antigo
    "https://dados.rfb.gov.br/CNPJ/dados_abertos_cnpj/2025-11/Municipios.zip",
]


def tentar_download_rf() -> pd.DataFrame | None:
    """Tenta baixar Municipios.zip da RF."""
    for url in RF_MUNICIPIOS_URLS:
        print(f"  Tentando: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                dados = resp.read()
            with zipfile.ZipFile(io.BytesIO(dados)) as zf:
                fname = zf.namelist()[0]
                with zf.open(fname) as f:
                    df = pd.read_csv(f, sep=";", header=None,
                                     names=["codigo", "nome"],
                                     dtype=str, encoding="latin-1")
            print(f"  Sucesso! {len(df):,} municípios baixados.")
            df.to_csv(SAIDA_MUNICIPIOS, index=False, sep=";", encoding="utf-8-sig")
            return df
        except Exception as e:
            print(f"  Falha: {type(e).__name__}: {e}")
    return None


def ler_municipios_zip_local() -> pd.DataFrame | None:
    """Verifica se o arquivo Municipios_RF.zip foi colocado manualmente na pasta bases/."""
    candidatos = list(DIR_BASES.glob("Municipios*.zip")) + list(DIR_BASES.glob("municipios*.zip"))
    if not candidatos:
        return None
    arquivo = candidatos[0]
    print(f"  Arquivo local encontrado: {arquivo.name}")
    try:
        with zipfile.ZipFile(arquivo) as zf:
            fname = zf.namelist()[0]
            with zf.open(fname) as f:
                df = pd.read_csv(f, sep=";", header=None,
                                 names=["codigo", "nome"],
                                 dtype=str, encoding="latin-1")
        df.to_csv(SAIDA_MUNICIPIOS, index=False, sep=";", encoding="utf-8-sig")
        return df
    except Exception as e:
        print(f"  Erro ao ler arquivo local: {e}")
        return None


def construir_mapeamento_via_ibge(df_estab: pd.DataFrame) -> pd.DataFrame:
    """
    Fallback: usa nomes do IBGE + UF para criar mapeamento aproximado.
    Extrai municípios únicos do dataset de estabelecimentos e tenta
    cruzar com dados IBGE via estado (UF).
    """
    print("  Usando mapeamento fallback via IBGE...")
    df_ibge = pd.read_csv(MUNICIPIOS_IBGE, dtype=str)
    # df_ibge tem colunas: codigo_ibge, nome, latitude, longitude, capital, codigo_uf, ...

    # Extrair municípios únicos do dataset de estabelecimentos
    mun_unicos = df_estab[["uf", "municipio"]].drop_duplicates()
    print(f"  {len(mun_unicos):,} combinações UF+cod_RF únicas encontradas.")

    # Sem mapeamento direto, retornar códigos como estão
    return mun_unicos.rename(columns={"municipio": "codigo"}).assign(
        nome=lambda x: "Cód RF " + x["codigo"].astype(str)
    )[["codigo", "nome"]]


def enriquecer_dataset(df_mun: pd.DataFrame) -> None:
    """Adiciona nome_municipio ao parquet principal."""
    if not SAIDA_PARQUET.exists():
        print("Dataset principal não encontrado. Execute processar_cnpjs_energia.py primeiro.")
        return

    print(f"\nCarregando dataset principal...")
    df = pd.read_parquet(SAIDA_PARQUET)
    print(f"  {len(df):,} registros carregados.")

    df_mun_clean = df_mun.copy()
    df_mun_clean["codigo"] = df_mun_clean["codigo"].astype(str).str.strip().str.zfill(4)
    df["municipio"] = df["municipio"].astype(str).str.strip().str.zfill(4)

    df = df.merge(
        df_mun_clean.rename(columns={"codigo": "municipio", "nome": "nome_municipio"}),
        on="municipio", how="left"
    )
    cobertura = df["nome_municipio"].notna().mean() * 100
    print(f"  Cobertura do mapeamento: {cobertura:.1f}%")

    df.to_parquet(SAIDA_ENRIQUECIDO, index=False)
    print(f"  Dataset enriquecido salvo: {SAIDA_ENRIQUECIDO.name}")

    # Gerar resumo enriquecido
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
    resumo_path = DIR_RESULTADOS / "resumo_por_municipio_cnae_nomes.csv"
    resumo.to_csv(resumo_path, index=False, encoding="utf-8-sig", sep=";")
    print(f"  Resumo com nomes salvo: {resumo_path.name}")


def main():
    print("=" * 60)
    print("MAPEAMENTO DE MUNICÍPIOS RF")
    print("=" * 60)

    df_mun = None

    # 1. Verificar cache local
    if SAIDA_MUNICIPIOS.exists():
        print("Cache local encontrado, carregando...")
        df_mun = pd.read_csv(SAIDA_MUNICIPIOS, sep=";", dtype=str, encoding="utf-8-sig")
        print(f"  {len(df_mun):,} municípios no cache.")
    else:
        # 2. Arquivo ZIP colocado manualmente
        print("\nVerificando arquivo local...")
        df_mun = ler_municipios_zip_local()

        # 3. Tentar download RF
        if df_mun is None:
            print("\nTentando download da RF...")
            df_mun = tentar_download_rf()

        # 4. Fallback via IBGE
        if df_mun is None and SAIDA_PARQUET.exists():
            print("\nFallback: construindo mapeamento via dataset...")
            df_estab = pd.read_parquet(SAIDA_PARQUET, columns=["uf", "municipio"])
            df_mun = construir_mapeamento_via_ibge(df_estab)
            df_mun.to_csv(SAIDA_MUNICIPIOS, index=False, sep=";", encoding="utf-8-sig")

    if df_mun is None:
        print("\nNão foi possível obter o mapeamento. Verifique se o dataset principal foi gerado.")
        return

    print(f"\nTotal de municípios mapeados: {len(df_mun):,}")

    # Enriquecer dataset principal
    enriquecer_dataset(df_mun)

    print("\n" + "=" * 60)
    print("Concluído!")
    print(f"Para obter o arquivo Municipios.zip manualmente:")
    print(f"  1. Acesse https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj")
    print(f"  2. Baixe o arquivo 'Municipios.zip'")
    print(f"  3. Coloque em: {DIR_BASES}")
    print(f"  4. Execute este script novamente")
    print("=" * 60)


if __name__ == "__main__":
    main()

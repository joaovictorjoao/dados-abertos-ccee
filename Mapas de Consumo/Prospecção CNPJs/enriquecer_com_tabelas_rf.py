"""
Processa os arquivos de tabelas RF baixados (MUNICCSV, MOTICSV, etc.)
e enriquece o dataset de estabelecimentos com nomes reais.
"""
from pathlib import Path
import pandas as pd

BASE_PROJETO   = Path(__file__).parent
DIR_BASES      = BASE_PROJETO / "bases"
DIR_RESULTADOS = BASE_PROJETO / "resultados"

# Arquivos baixados (estão na raiz da pasta do projeto)
ARQUIVO_MUNIC  = BASE_PROJETO / "F.K03200$Z.D60509.MUNICCSV"
ARQUIVO_MOTIC  = BASE_PROJETO / "F.K03200$Z.D60509.MOTICSV"
ARQUIVO_NATJU  = BASE_PROJETO / "F.K03200$Z.D60509.NATJUCSV"

PARQUET_PRINCIPAL = DIR_RESULTADOS / "estabelecimentos_energia.parquet"

def ler_tabela_rf(arquivo: Path, cols: list[str]) -> pd.DataFrame:
    """Lê arquivo de tabela RF (sem cabeçalho, sep=;, encoding latin-1)."""
    df = pd.read_csv(
        arquivo, sep=";", header=None, names=cols,
        dtype=str, encoding="latin-1", quoting=1  # QUOTE_ALL
    )
    # Limpar aspas residuais
    for col in cols:
        df[col] = df[col].str.strip().str.strip('"')
    return df

def salvar_municipios(df_mun: pd.DataFrame):
    """Salva tabela de municípios no formato padrão do projeto."""
    dest = DIR_BASES / "municipios_rf.csv"
    df_mun.to_csv(dest, index=False, sep=";", encoding="utf-8-sig")
    print(f"  Salvo: {dest} ({len(df_mun):,} municípios)")

def enriquecer_dataset(df_mun: pd.DataFrame) -> pd.DataFrame:
    """Adiciona nome_municipio ao dataset principal."""
    print(f"\nCarregando dataset principal...")
    df = pd.read_parquet(PARQUET_PRINCIPAL)
    print(f"  {len(df):,} registros")

    mun_map = df_mun.set_index("codigo")["nome"].to_dict()

    df["municipio"] = df["municipio"].astype(str).str.strip().str.zfill(4)
    df["nome_municipio"] = df["municipio"].map(mun_map)

    cobertura = df["nome_municipio"].notna().mean() * 100
    print(f"  Cobertura: {cobertura:.1f}%")

    dest = DIR_RESULTADOS / "estabelecimentos_energia_com_municipios.parquet"
    df.to_parquet(dest, index=False)
    print(f"  Salvo: {dest.name}")
    return df

def gerar_rankings_com_nomes(df: pd.DataFrame):
    """Gera CSVs de ranking já com nomes de municípios."""
    df["demanda_estimada_kW"] = df["cnae_divisao"].map({
        "05":850,"06":2000,"07":1500,"08":800,"09":300,
        "10":600,"11":500,"12":800,"13":700,"14":300,
        "15":400,"16":500,"17":1200,"18":400,"19":2000,
        "20":1500,"21":1000,"22":800,"23":1200,"24":3000,
        "25":600,"26":500,"27":700,"28":800,"29":1500,
        "30":1000,"31":400,"32":350,"33":400,
        "35":5000,"36":1500,"37":800,"38":600,"39":400,
        "41":300,"42":500,"43":200,
        "46":400,"47":300,
        "49":250,"50":500,"51":2000,"52":600,
        "55":300,
        "61":1000,"62":400,"63":1500,
        "85":250,"86":600,"93":400,
    }).fillna(300)

    # Top 200 municípios
    df_mun = (
        df.groupby(["uf", "municipio", "nome_municipio"])
        .agg(
            total_empresas=("cnpj", "count"),
            tier1=("cnae_tier", lambda x: (x == 1).sum()),
            tier2=("cnae_tier", lambda x: (x == 2).sum()),
            demanda_total_MW=("demanda_estimada_kW", lambda x: round(x.sum() / 1000)),
        )
        .reset_index()
        .sort_values("demanda_total_MW", ascending=False)
        .head(200)
    )
    dest = DIR_RESULTADOS / "ranking_municipios_top200.csv"
    df_mun.to_csv(dest, index=False, sep=";", encoding="utf-8-sig")
    print(f"\nTop 200 municípios salvo: {dest.name}")
    print("\nTop 30 municípios por demanda potencial estimada:")
    print(df_mun.head(30).to_string(index=False))

    # Resumo completo por município + CNAE com nomes
    df_resumo = (
        df.groupby(["uf", "municipio", "nome_municipio", "cnae_divisao", "cnae_descricao", "cnae_tier"], dropna=False)
        .agg(
            total_empresas=("cnpj", "count"),
            matrizes=("identificador_matriz_filial", lambda x: (x == "1").sum()),
        )
        .reset_index()
        .sort_values(["cnae_tier", "total_empresas"], ascending=[True, False])
    )
    dest2 = DIR_RESULTADOS / "resumo_municipio_cnae_completo.csv"
    df_resumo.to_csv(dest2, index=False, sep=";", encoding="utf-8-sig")
    print(f"\nResumo completo salvo: {dest2.name} ({len(df_resumo):,} linhas)")

def main():
    print("=" * 60)
    print("ENRIQUECIMENTO COM TABELAS RF")
    print("=" * 60)

    # 1. Ler tabela de municípios
    print("\n1. Lendo tabela de municípios...")
    df_mun = ler_tabela_rf(ARQUIVO_MUNIC, ["codigo", "nome"])
    df_mun["codigo"] = df_mun["codigo"].str.zfill(4)
    print(f"  {len(df_mun):,} municípios carregados")
    print(f"  Exemplos:\n{df_mun.head(5).to_string(index=False)}")
    salvar_municipios(df_mun)

    # 2. Ler e salvar outras tabelas (para uso futuro)
    if ARQUIVO_MOTIC.exists():
        df_motic = ler_tabela_rf(ARQUIVO_MOTIC, ["codigo", "descricao"])
        df_motic.to_csv(DIR_BASES / "motivos_rf.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"\n2. Motivos RF salvo ({len(df_motic)} registros)")

    if ARQUIVO_NATJU.exists():
        df_natju = ler_tabela_rf(ARQUIVO_NATJU, ["codigo", "descricao"])
        df_natju.to_csv(DIR_BASES / "natureza_juridica_rf.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"   Natureza Jurídica RF salvo ({len(df_natju)} registros)")

    # 3. Enriquecer dataset principal
    print("\n3. Enriquecendo dataset principal com nomes de municípios...")
    df = enriquecer_dataset(df_mun)

    # 4. Gerar rankings com nomes
    print("\n4. Gerando rankings com nomes...")
    gerar_rankings_com_nomes(df)

    print("\n" + "=" * 60)
    print("Concluído!")
    print("=" * 60)

if __name__ == "__main__":
    main()

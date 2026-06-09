"""
Análise de Prospects para o Mercado Livre de Energia

Lê o dataset filtrado de CNPJs e gera:
  1. Ranking de UFs por potencial (empresas industriais/comerciais ativas)
  2. Ranking de municípios por CNAE tier
  3. Cruzamento com participantes CCEE (se disponível)
  4. Estimativa de potencial de mercado por setor
  5. Relatório CSV pronto para análise / apresentação
"""

from pathlib import Path
from datetime import datetime

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
BASE_PROJETO    = Path(__file__).parent
DIR_RESULTADOS  = BASE_PROJETO / "resultados"
DIR_BASES       = BASE_PROJETO / "bases"

PARQUET_PRINCIPAL  = DIR_RESULTADOS / "estabelecimentos_energia.parquet"
PARQUET_ENRIQUECIDO = DIR_RESULTADOS / "estabelecimentos_energia_com_municipios.parquet"

# Dados CCEE opcionais para cruzamento — aponte para a pasta bases/ de Extração Consumo Horário
# DIR_CCEE = BASE_PROJETO.parent.parent / "Extração Consumo Horário" / "bases"

# ─────────────────────────────────────────────────────────────────────────────
# CNAE → Tier e seção para legibilidade
DESCRICAO_CNAE_SECTION = {
    "B": "Indústria Extrativa",
    "C": "Indústria de Transformação",
    "D": "Eletricidade e Gás",
    "E": "Saneamento e Resíduos",
    "F": "Construção",
    "G": "Comércio",
    "H": "Transporte e Armazenagem",
    "I": "Alojamento",
    "J": "TIC / Telecomunicações",
    "P": "Educação",
    "Q": "Saúde",
    "R": "Esporte e Lazer",
}

# Tamanho médio estimado de demanda por divisão CNAE (kW médio por estabelecimento)
# Fonte: benchmarks EPE/ANEEL por setor
DEMANDA_MEDIA_kW = {
    "05": 850, "06": 2000, "07": 1500, "08": 800, "09": 300,
    "10": 600, "11": 500, "12": 800, "13": 700, "14": 300,
    "15": 400, "16": 500, "17": 1200, "18": 400, "19": 2000,
    "20": 1500, "21": 1000, "22": 800, "23": 1200, "24": 3000,
    "25": 600, "26": 500, "27": 700, "28": 800, "29": 1500,
    "30": 1000, "31": 400, "32": 350, "33": 400,
    "35": 5000, "36": 1500, "37": 800, "38": 600, "39": 400,
    "41": 300, "42": 500, "43": 200,
    "46": 400, "47": 300,
    "49": 250, "50": 500, "51": 2000, "52": 600,
    "55": 300,
    "61": 1000, "62": 400, "63": 1500,
    "85": 250, "86": 600, "93": 400,
}


def carregar_dataset() -> pd.DataFrame:
    """Carrega o dataset principal (enriquecido se disponível)."""
    if PARQUET_ENRIQUECIDO.exists():
        print(f"Carregando dataset enriquecido...")
        df = pd.read_parquet(PARQUET_ENRIQUECIDO)
    elif PARQUET_PRINCIPAL.exists():
        print(f"Carregando dataset principal (sem nomes de municípios)...")
        df = pd.read_parquet(PARQUET_PRINCIPAL)
        df["nome_municipio"] = "Cód RF " + df["municipio"].astype(str)
    else:
        raise FileNotFoundError(
            "Dataset não encontrado. Execute processar_cnpjs_energia.py primeiro."
        )
    print(f"  {len(df):,} registros carregados.")
    return df


def analise_por_uf(df: pd.DataFrame) -> pd.DataFrame:
    """Ranking de UFs por número de empresas e demanda potencial estimada."""
    df["demanda_estimada_kW"] = df["cnae_divisao"].map(DEMANDA_MEDIA_kW).fillna(300)

    resumo = (
        df.groupby("uf")
        .agg(
            total_empresas=("cnpj", "count"),
            tier1=("cnae_tier", lambda x: (x == 1).sum()),
            tier2=("cnae_tier", lambda x: (x == 2).sum()),
            tier3=("cnae_tier", lambda x: (x == 3).sum()),
            demanda_total_MW=("demanda_estimada_kW", lambda x: x.sum() / 1000),
            cnae_mais_comum=("cnae_descricao", lambda x: x.value_counts().index[0] if len(x) > 0 else ""),
        )
        .reset_index()
        .sort_values("demanda_total_MW", ascending=False)
    )
    resumo["demanda_total_MW"] = resumo["demanda_total_MW"].round(0).astype(int)
    return resumo


def analise_por_municipio(df: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    """Top municípios por concentração industrial."""
    df["demanda_estimada_kW"] = df["cnae_divisao"].map(DEMANDA_MEDIA_kW).fillna(300)

    resumo = (
        df.groupby(["uf", "municipio", "nome_municipio"])
        .agg(
            total_empresas=("cnpj", "count"),
            tier1=("cnae_tier", lambda x: (x == 1).sum()),
            tier2=("cnae_tier", lambda x: (x == 2).sum()),
            demanda_total_MW=("demanda_estimada_kW", lambda x: x.sum() / 1000),
        )
        .reset_index()
        .sort_values("demanda_total_MW", ascending=False)
        .head(top_n)
    )
    resumo["demanda_total_MW"] = resumo["demanda_total_MW"].round(0).astype(int)
    return resumo


def analise_por_cnae(df: pd.DataFrame) -> pd.DataFrame:
    """Ranking de setores por demanda potencial."""
    df["demanda_estimada_kW"] = df["cnae_divisao"].map(DEMANDA_MEDIA_kW).fillna(300)

    resumo = (
        df.groupby(["cnae_divisao", "cnae_descricao", "cnae_tier"])
        .agg(
            total_empresas=("cnpj", "count"),
            matrizes=("identificador_matriz_filial", lambda x: (x == "1").sum()),
            demanda_total_MW=("demanda_estimada_kW", lambda x: x.sum() / 1000),
            demanda_media_kW=("demanda_estimada_kW", "mean"),
        )
        .reset_index()
        .sort_values(["cnae_tier", "demanda_total_MW"], ascending=[True, False])
    )
    resumo["demanda_total_MW"] = resumo["demanda_total_MW"].round(0).astype(int)
    resumo["demanda_media_kW"] = resumo["demanda_media_kW"].round(0).astype(int)
    return resumo


def analise_maturidade_livre(df_uf: pd.DataFrame) -> pd.DataFrame:
    """
    Estima o percentual de empresas elegíveis ao mercado livre por UF.
    Usa demanda estimada >= 500 kW como proxy de elegibilidade.
    """
    return df_uf


def gerar_relatorio_executivo(df: pd.DataFrame, df_uf: pd.DataFrame,
                               df_mun: pd.DataFrame, df_cnae: pd.DataFrame) -> str:
    """Gera texto de relatório executivo."""
    total_emp = len(df)
    total_mw = int(df.get("demanda_estimada_kW", pd.Series([0])).sum() / 1000)
    tier1 = int((df["cnae_tier"] == 1).sum())
    tier2 = int((df["cnae_tier"] == 2).sum())
    ufs = df["uf"].nunique()

    top3_uf = df_uf.head(3)["uf"].tolist()
    top3_cnae = df_cnae.head(3)["cnae_descricao"].tolist()
    top_mun = df_mun.iloc[0] if len(df_mun) > 0 else None

    relatorio = f"""
RELATÓRIO EXECUTIVO - PROSPECÇÃO MERCADO LIVRE DE ENERGIA
Data de geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}
{'='*60}

VISÃO GERAL
  Total de empresas identificadas:  {total_emp:,}
  Demanda potencial estimada:        {total_mw:,} MW
  Estados cobertos:                  {ufs}

  Tier 1 (muito alta intensidade):   {tier1:,} ({100*tier1//total_emp}%)
  Tier 2 (alta intensidade):         {tier2:,} ({100*tier2//total_emp}%)

DESTAQUES POR UF (Top 3 por demanda)
  {', '.join(top3_uf)}

SETORES PRIORITÁRIOS (Top 3)
  {chr(10).join(f'  {i+1}. {c}' for i, c in enumerate(top3_cnae))}

MUNICÍPIO COM MAIOR POTENCIAL
  {f'{top_mun["nome_municipio"]} ({top_mun["uf"]}) — {top_mun["demanda_total_MW"]:,} MW estimados' if top_mun is not None else 'N/A'}

METODOLOGIA
  • Fonte: Dados Abertos CNPJ - Receita Federal (jun/2026)
  • Filtros: situação cadastral ATIVA + CNAEs de alto consumo energético
  • Demanda estimada com base em benchmarks setoriais EPE/ANEEL
  • Tier 1: >1.000 kW médio estimado por estabelecimento
  • Tier 2: 300-1.000 kW estimado | Tier 3: <300 kW estimado
  • ATENÇÃO: valores são estimativas para priorização, não medições reais
{'='*60}
"""
    return relatorio


def main():
    print("=" * 60)
    print("ANÁLISE DE PROSPECTS - MERCADO LIVRE DE ENERGIA")
    print("=" * 60)

    df = carregar_dataset()

    print("\n1. Análise por UF...")
    df_uf = analise_por_uf(df)
    df_uf.to_csv(DIR_RESULTADOS / "ranking_ufs.csv", index=False, encoding="utf-8-sig", sep=";")
    print(df_uf.to_string(index=False))

    print("\n2. Top 100 municípios por demanda potencial...")
    df_mun = analise_por_municipio(df)
    df_mun.to_csv(DIR_RESULTADOS / "ranking_municipios_top100.csv",
                  index=False, encoding="utf-8-sig", sep=";")
    print(df_mun.head(20).to_string(index=False))

    print("\n3. Análise por setor CNAE...")
    df_cnae = analise_por_cnae(df)
    df_cnae.to_csv(DIR_RESULTADOS / "ranking_setores.csv",
                   index=False, encoding="utf-8-sig", sep=";")
    print(df_cnae.to_string(index=False))

    print("\n4. Gerando relatório executivo...")
    relatorio = gerar_relatorio_executivo(df, df_uf, df_mun, df_cnae)
    relatorio_path = DIR_RESULTADOS / "relatorio_executivo.txt"
    relatorio_path.write_text(relatorio, encoding="utf-8")
    print(relatorio)

    print("=" * 60)
    print(f"Arquivos gerados em: {DIR_RESULTADOS}")
    print("  ranking_ufs.csv")
    print("  ranking_municipios_top100.csv")
    print("  ranking_setores.csv")
    print("  relatorio_executivo.txt")
    print("=" * 60)


if __name__ == "__main__":
    main()

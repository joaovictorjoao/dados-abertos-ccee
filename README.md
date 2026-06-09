# Dados Abertos CCEE — Análise do Mercado Livre de Energia

Suite de análise de dados para identificação e visualização de oportunidades no Mercado Livre de Energia (MLE) brasileiro, desenvolvida pela [Grugeen Consultoria](https://grugeen.eng.br).

Combina dados públicos da CCEE (consumo horário de agentes) com a base de CNPJs da Receita Federal para mapear concentração industrial e lacunas de atendimento por município.

---

## Funcionalidades

- **Extração de consumo horário** — filtra e exporta registros do arquivo CCEE (~34 milhões de linhas) por carga ou CNPJ, sem carregar tudo em memória
- **Mapa interativo de consumo mensal** — dashboard HTML com 4 abas: consumo total por UF, consumo por município, consumo per capita e penetração ACL (consumidores/100k hab.)
- **Mapa de prospecção por CNPJ** — dashboard HTML com 5 abas cruzando base da Receita Federal com dados de consumo CCEE para identificar municípios com potencial industrial ainda fora do mercado livre
- **Pipeline de processamento de CNPJs** — extrai, filtra e enriquece a base de estabelecimentos da RF (~15M registros) classificando por setor e potencial de demanda

---

## Estrutura do Projeto

```
Dados Abertos CCEE/
│
├── Extração Consumo Horário/
│   ├── consumo_pico_por_carga.py          # Pico mensal por código de carga → Excel
│   ├── consumo_completo_por_cnpj.py       # Histórico horário por CNPJ → CSV
│   ├── consumo_horario_perfil_agente_202604.csv.gz  # Dado CCEE (não incluído no repo)
│   ├── bases/                             # Saídas geradas (Excel, CSV)
│   └── logs/                             # Logs de execução com timestamp
│
└── Mapas de Consumo/
    ├── mapa_consumo_mensal.py             # Dashboard de consumo (4 abas)
    ├── mapa_prospecao_cnpjs.py            # Dashboard de prospecção (5 abas)
    ├── Mapas/                             # HTMLs, GeoJSONs e CSVs em cache
    ├── Logs/                             # Logs de execução
    └── Prospecção CNPJs/
        ├── processar_cnpjs_energia.py     # Extrai e filtra base RF
        ├── enriquecer_com_tabelas_rf.py   # Enriquece com nomes de municípios
        ├── analisar_prospects.py          # Relatório de inteligência de mercado
        ├── obter_municipios_rf.py         # Baixa tabela de municípios da RF
        ├── bases/                         # Parquets intermediários
        ├── resultados/                    # CSVs de ranking e relatório executivo
        └── logs/                         # Logs de execução
```

---

## Requisitos

- Python 3.9+
- Dependências:

```bash
pip install pandas duckdb openpyxl plotly numpy
```

**Opcional (aceleração):**
```bash
pip install duckdb polars   # até 30x mais rápido no processamento do CSV CCEE
```

---

## Dados Necessários

### 1. Consumo Horário CCEE

Baixar em: [CCEE — Dados Abertos](https://www.ccee.org.br/pt/dados-e-ferramentas/dados-abertos/)

- Arquivo: `consumo_horario_perfil_agente_AAAAMM.csv.gz`
- Colocar em: `Extração Consumo Horário/`
- Tamanho típico: ~418 MB (comprimido) / ~7,5 GB descomprimido, ~34 milhões de linhas

### 2. Base de CNPJs da Receita Federal

Baixar em: [Dados Abertos RF — Empresas](https://dadosabertos.rfb.gov.br/CNPJ/)

- Arquivo: `Base_CNPJs.7z` (contém 10 arquivos ZIP de Estabelecimentos)
- Colocar em: `Mapas de Consumo/Prospecção CNPJs/`
- Requer: `7-Zip` instalado e disponível no PATH (`7z`)

---

## Uso

### Extração de consumo horário

```bash
# Pico mensal por código de carga
cd "Extração Consumo Horário"
python consumo_pico_por_carga.py

# Histórico completo de um CNPJ
python consumo_completo_por_cnpj.py
# → Solicita CNPJ interativamente (com ou sem formatação)
# → Ou: python consumo_completo_por_cnpj.py 12.345.678/0001-99
```

### Pipeline de CNPJs

```bash
cd "Mapas de Consumo/Prospecção CNPJs"

# 1. Extrai e filtra estabelecimentos de alto consumo
python processar_cnpjs_energia.py

# 2. Enriquece com nomes de municípios e gera rankings
python enriquecer_com_tabelas_rf.py

# 3. (Opcional) Relatório executivo de mercado
python analisar_prospects.py
```

### Geração dos dashboards HTML

```bash
cd "Mapas de Consumo"

# Mapa de consumo mensal (baixa GeoJSON/IBGE automaticamente)
python mapa_consumo_mensal.py
# → Gera: Mapas/mapa_consumo_AAAAMM.html

# Mapa de prospecção por CNPJ (requer pipeline acima concluído)
python mapa_prospecao_cnpjs.py
# → Gera: Mapas/mapa_prospecao_cnpjs.html
```

Os arquivos HTML gerados são autossuficientes — podem ser abertos no navegador sem servidor.

---

## Dashboards Gerados

### Mapa de Consumo Mensal (`mapa_consumo_AAAAMM.html`)

| Aba | Conteúdo |
|-----|----------|
| Por Estado | Consumo total ACL em GWh por UF (coroplético) |
| Por Município | Consumo total ACL em GWh por município |
| Per Capita | Consumo MWh/habitante (normalizado pelo Censo IBGE 2022) |
| Penetração ACL | Consumidores por 100 mil habitantes (saturação de mercado) |

Filtros interativos: Região → UF → Distribuidora. Alterna entre mapa e tabela.

### Mapa de Prospecção (`mapa_prospecao_cnpjs.html`)

| Aba | Conteúdo |
|-----|----------|
| Tier 1 | Empresas industriais de altíssimo consumo por município |
| Total | Todos os setores combinados |
| Demanda Estimada | MW estimado por município (benchmarks EPE/ANEEL por CNAE) |
| Densidade Industrial | Empresas por 1.000 habitantes |
| Oportunidades | Municípios com base industrial mas zero consumidores ACL |

---

## Classificação de Setores (CNAE)

Os estabelecimentos da RF são classificados em 3 tiers de potencial de consumo:

| Tier | Exemplos de Setores |
|------|---------------------|
| **Tier 1** — Muito alto | Mineração, petróleo/gás, alimentos/bebidas, química, metalurgia, utilidades, telecom |
| **Tier 2** — Alto | Têxtil, madeira, papel, manufatura, transporte aéreo, saúde |
| **Tier 3** — Moderado | Varejo, TI, educação |

A estimativa de demanda (MW) usa benchmarks de kW/estabelecimento por divisão CNAE baseados em referências da EPE e ANEEL.

---

## Performance

| Script | Método | Tempo típico |
|--------|--------|--------------|
| `consumo_pico_por_carga.py` | Python streaming | ~2,5–3 min |
| `consumo_pico_por_carga.py` | DuckDB | ~30–60 s |
| `consumo_completo_por_cnpj.py` | Python streaming | ~2,5–3 min |
| `consumo_completo_por_cnpj.py` | DuckDB | ~10–15 s |
| `processar_cnpjs_energia.py` | pandas | ~5–10 min |
| `mapa_consumo_mensal.py` | pandas + Plotly | ~3–5 min (1ª execução) |

Na primeira execução, `mapa_consumo_mensal.py` baixa GeoJSONs do IBGE e do GitHub (~200 MB). Nas execuções seguintes, usa cache local.

---

## Geocodificação

O mapeamento entre municípios do arquivo CCEE e os códigos IBGE tem taxa de acerto de ~99% (3.020 de 3.062 municípios), usando normalização Unicode e tabela de aliases para variações conhecidas de nomes (acentuação, apóstrofes, abreviações).

---

## Logs

Todos os scripts gravam logs com timestamp em suas respectivas pastas `logs/`. Consulte os logs para:
- Diagnóstico de erros de execução
- Monitoramento de performance
- Auditoria de arquivos processados

---

## Limitações Conhecidas

- O arquivo CCEE (`consumo_horario_perfil_agente_202604.csv.gz`) **não está incluído** no repositório por seu tamanho. Deve ser baixado diretamente da CCEE.
- A base de CNPJs da RF (`Base_CNPJs.7z`) também não está incluída — baixar no portal de Dados Abertos da RF.
- Estimativas de demanda (MW) são orientativas; não substituem medição real.
- GeoJSON de municípios obtido via API pública do IBGE — requer internet na primeira execução.

---

## Licença

Este projeto é de uso interno da Grugeen Consultoria. Consulte a empresa para informações sobre licenciamento e redistribuição.

---

## Contato

**Grugeen Consultoria Ltda**  
[grugeen.eng.br](https://grugeen.eng.br) · joao@grugeen.eng.br

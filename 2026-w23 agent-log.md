## 2026-06-02

- Mapa interativo de consumo mensal no Brasil
	- Usuário pediu visualização do consumo total mensal em mapa interativo do Brasil a partir do dataset CCEE com localização por consumidor.
	- Dataset principal: `consumo_horario_perfil_agente_202604.csv.gz` (418 MB, ~34M linhas, colunas CIDADE_CARGA e ESTADO_CARGA disponíveis).
	- Criado `mapa_consumo_mensal.py`: DuckDB agrega consumo ACL por estado (27 registros) e por cidade (3.062 municípios) em ~20s total.
	- GeoJSON dos estados obtido da API oficial do IBGE (cacheado localmente); municípios com lat/lon de banco estático do IBGE via GitHub (kelvins/municipios-brasileiros, 5.571 registros).
	- 99% de geocodificação automática (3.020/3.062 cidades); 42 cidades não encontradas por variações de apostrofe (ex: "D' OESTE" vs "D'OESTE").
	- Saída: 3 HTMLs interativos com Plotly em `mapas/` — coroplético por estado, bolhas por município, e dashboard combinado com abas.
	- CHUNK: script mapa_consumo_mensal.py completo com DuckDB + Plotly + geocodificação IBGE

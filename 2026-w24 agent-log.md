## 2026-06-08

- Reorganização da pasta Consumo Horário — bases geradas separadas em subpasta
	- Identificados arquivos dispensáveis: `__pycache__/`, script de rascunho `consumo_horario_perfilagente.py` (caminhos placeholder, sem logging), e CSV com nome UUID gerado pelo DuckDB.
	- Criada pasta `bases/` dentro de `Consumo Horário` para centralizar outputs dos scripts.
	- Movidos para `bases/`: `consumo_pico_por_carga_202603.xlsx`, dois CSVs de CNPJ e o CSV UUID.
	- Corrigido bug no `consumo_pico_por_carga.py`: `ARQUIVO_SAIDA` apontava para pasta pai `Dados Abertos CCEE` em vez de `Consumo Horário/bases/`.
	- Atualizado `consumo_completo_por_cnpj.py`: `PASTA_SAIDA` passa a usar `bases/` automaticamente, com `mkdir(exist_ok=True)` na geração do nome do arquivo.

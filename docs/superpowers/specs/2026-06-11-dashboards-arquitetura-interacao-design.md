# Sub-projeto A — Arquitetura de Interação dos Dashboards

**Data:** 2026-06-11
**Autor:** Grugeen Consultoria (João Victor) + Claude Code
**Status:** Design aprovado em brainstorming — aguardando revisão do spec
**Escopo:** Refatoração da camada de geração e interação dos dashboards HTML
(`mapa_consumo_mensal.py` e `mapa_prospecao_cnpjs.py`)

---

## 1. Contexto e Problema

A suíte de análise do Mercado Livre de Energia gera dois dashboards HTML interativos
a partir de dados públicos da CCEE e da Receita Federal:

- **Consumo mensal** (`mapa_consumo_mensal.py`, 1.943 linhas) — 4 abas.
- **Prospecção por CNPJ** (`mapa_prospecao_cnpjs.py`, 1.490 linhas) — 5 abas.

### Dores identificadas (priorizadas pelo usuário)

1. **UX dos dashboards** — hovers, filtros e mapas não se comportam como desejado;
   bugs recorrentes (zoom que não reseta/preserva, municípios em branco no mapa de
   lacunas, filtros que param de funcionar); e ajustes de filtro pendentes que ainda
   não foram iniciados por receio de quebrar o que existe.
2. **Confiabilidade dos dados** — geocodificação e estimativas de demanda (MW).
   **Fora do escopo deste sub-projeto** (será o Sub-projeto B).

### Causa-raiz

Cada script concentra uma função monolítica `_salvar_dashboard` (~600 e ~440 linhas)
que é uma f-string com **HTML + CSS + JavaScript embutidos**. Há ~134 trechos de
lógica JavaScript (manipulação de DOM, eventos, `Plotly.relayout`, filtros) vivendo
dentro de strings Python — **não lintáveis, não testáveis, não depuráveis** pelas
ferramentas normais. O escape de chaves (`{{ }}`) das f-strings é fonte adicional de
erro. Resultado: cada correção arrisca quebrar outra coisa (ciclo reativo observado:
`fix_zoom.py`, `fix_blank.py`, `fix_final.py`, ...).

**Agravante transversal:** duplicação massiva — ~15 funções auxiliares idênticas
copiadas entre os dois scripts (`_fetch`, `_baixar_recurso`, `_normalizar`,
`_geocodificar`, `_setup_logging`, `_br`, `_fmt_*`, `_geo_layout`, `_fig_layout`,
`_prevent_sleep`, `_restore_sleep`, `_logo_data_uri`).

---

## 2. Objetivos e Não-objetivos

### Objetivos

- Extrair HTML/CSS/JS das strings Python para **arquivos reais**, lintáveis e testáveis.
- Tornar hovers, filtros e mapas **confiáveis** e corrigir os bugs recorrentes na raiz.
- Permitir **adicionar/alterar filtros com segurança** (novos critérios, filtros
  dependentes/cascata, hover/seleção com drill-down, sincronização mapa↔tabela,
  persistência e exportação).
- **Eliminar a duplicação** entre os dois dashboards via camada compartilhada.
- Preservar o uso atual: saída em **HTML que abre sem servidor**.

### Não-objetivos (YAGNI)

- Não introduzir toolchain Node/npm nem framework de front (Vite/Alpine/Preact).
- Não revisar confiabilidade de dados (geocodificação, estimativas MW) — Sub-projeto B.
- Não alterar a lógica de negócio das agregações nem o visual final na fase de migração
  (mudanças de comportamento só após paridade com o baseline).
- Não migrar para app web servido.

### Critérios de sucesso

- Os dois dashboards geram saída visualmente idêntica ao baseline atual após a migração.
- A lógica de filtro/interação tem testes automatizados que rodam sem navegador.
- Adicionar um novo critério de filtro não exige editar o JS de renderização.
- Zero código JavaScript dentro de f-strings Python.
- Nenhuma das ~15 funções auxiliares aparece duplicada.

---

## 3. Decisão de Arquitetura

**Abordagem escolhida:** assets separados (`.css`/`.js` reais) + injetor de dados em
Python + duplo modo de saída. Vanilla JS com estado central. Sem bundler/framework.

Alternativas consideradas e descartadas:

- **Toolchain de front (Vite/esbuild + Alpine/Preact):** mais robusto, porém traz
  Node/npm e build step a um projeto centrado em Python — over-engineering, já que o
  Plotly faz o trabalho pesado de renderização.
- **Apenas Jinja2:** elimina o escape `{{ }}` e deduplica, mas mantém o JS acoplado ao
  template, sem resolver a raiz (testabilidade do JS). É um subconjunto da escolhida.

**Restrição de distribuição:** o resultado deve abrir sem servidor. Usa-se `<script src>`
clássico (não módulos ES, que o `file://` bloqueia), e oferece-se um modo de saída que
**inlina** tudo num único `.html` portátil para envio a clientes.

---

## 4. Estrutura de Pastas

```
Mapas de Consumo/
│
├── grugeen_dashboards/                  # pacote Python (substitui os 2 monólitos)
│   ├── __init__.py
│   ├── comum/                           # camada COMPARTILHADA (mata a duplicação)
│   │   ├── http.py                      # _fetch, _baixar_recurso
│   │   ├── geo.py                       # _normalizar, _geocodificar, GeoJSON, municípios IBGE
│   │   ├── logging_setup.py             # _setup_logging
│   │   ├── formato.py                   # _br, _fmt_*  (formatação pt-BR)
│   │   ├── energia.py                   # _prevent_sleep / _restore_sleep
│   │   └── marca.py                     # logo, paleta, fontes Grugeen
│   │
│   ├── consumo/
│   │   ├── dados.py                     # agregações → DataFrames
│   │   └── contrato.py                  # DataFrame → dict JSON (o "contrato")
│   ├── prospeccao/
│   │   ├── dados.py
│   │   └── contrato.py
│   │
│   └── geracao/
│       ├── gerador.py                   # injeta dados+assets no template; 2 modos de saída
│       └── modelos.py                   # config das abas/mapas por dashboard
│
├── assets/                              # camada de APRESENTAÇÃO (front real)
│   ├── dashboard.css                    # CSS extraído (1 fonte, ambos dashboards)
│   ├── core/
│   │   ├── estado.js                    # filterState central
│   │   ├── filtros.js                   # filtros dependentes/cascata
│   │   ├── interacao.js                 # hover, seleção, drill-down, sync mapa↔tabela
│   │   ├── persistencia.js              # lembrar filtros + link compartilhável
│   │   ├── exportacao.js                # CSV / imagem
│   │   └── render.js                    # Plotly.react + troca mapa/tabela
│   └── template.html                    # esqueleto com marcadores de injeção
│
├── tests/
│   ├── test_contrato.py / test_geo.py   # pytest
│   └── core.test.js                     # lógica de filtro (Node, sem framework)
│
├── gerar_consumo.py                     # entrypoints finos (CLI)
└── gerar_prospecao.py
```

Os scripts atuais viram **entrypoints finos**: carregar dados → montar contrato →
chamar gerador.

---

## 5. Camada Python (dados + geração)

- **`comum/`** — as ~15 funções hoje duplicadas passam a existir uma única vez; ambos
  os dashboards importam do mesmo lugar.
- **`<dashboard>/dados.py`** — agregação pura (equivalente às atuais `_agregar_*`,
  `_calcular_*`), retornando DataFrames. Sem HTML.
- **`<dashboard>/contrato.py`** — converte DataFrames no dict JSON consumido pelo front.
  É a fronteira: Python não conhece DOM; JS não conhece pandas.
- **`geracao/gerador.py`** — função única que recebe (contrato JSON, figuras Plotly,
  config de abas) e produz a saída em dois modos:
  - `--modo arquivos`: escreve `dashboard.html` + `.js` + `.css` lado a lado (dia a dia).
  - `--modo unico`: inlina tudo num só `.html` portátil (entrega a cliente).
  Mesma fonte; a decisão ocorre apenas na geração.

---

## 6. Contrato de Dados (interface Python ↔ JS)

Um único objeto JSON injetado no HTML, com formato versionado e estável:

```js
window.GRUGEEN_DATA = {
  versao: 1,
  meta:    { dashboard: "consumo", referencia: "2026-04", gerado_em: "..." },
  filtros: {                         // define os filtros e suas dependências
    regiao:        { label: "Região", opcoes: [...] },
    uf:            { label: "UF", depende_de: "regiao", opcoes_por: {...} },
    distribuidora: { label: "Distribuidora", depende_de: "uf", opcoes_por: {...} }
    // novos critérios entram aqui sem tocar no JS de renderização
  },
  abas: [ { id, label, tipo: "mapa"|"tabela", ... } ],
  registros: [ ... ]                 // linhas já agregadas; filtro/recálculo no front
}
```

O JS lê o contrato e se monta sozinho. **Adicionar um filtro = acrescentar uma entrada
em `filtros`** no Python; `filtros.js` trata cascata/dependência genericamente.

> O schema exato de `abas`, `registros` e dos campos de cada filtro será fixado no
> plano de implementação, derivado do que os dashboards atuais já produzem (paridade
> com o baseline). Versionado por `versao` para evolução futura.

---

## 7. Camada Front-end

Ciclo previsível, estado central único:

```
filterState → recalcular opções dependentes → filtrar registros → render (Plotly.react + tabela)
     ↑                                                                      │
     └──────────────────── eventos (filtro, hover, clique, URL) ◄──────────┘
```

- **`estado.js`** — seleção de filtros + aba ativa + modo (mapa/tabela). Função única
  `setEstado(parcial)` dispara o re-render. Sem DOM espalhado.
- **`filtros.js`** — lê `filtros` do contrato e monta os selects; cascata genérica via
  `depende_de`. Novos critérios entram só pelo contrato.
- **`interacao.js`** — tooltip configurável, destaque no hover, clique para drill-down
  (clicar numa UF filtra para ela), sincronização mapa↔tabela.
- **`persistencia.js`** — serializa `filterState` na URL (`#regiao=S&uf=SC`) → link
  compartilhável que reabre com os filtros aplicados; restaura ao carregar.
- **`exportacao.js`** — exporta a seleção filtrada em CSV e a imagem do mapa em PNG
  (`Plotly.downloadImage`).
- **`render.js`** — usa `Plotly.react` (não recria o gráfico do zero) e controla
  explicitamente `uirevision` para corrigir o bug de zoom que não preserva/reseta.

Cada arquivo tem propósito único — o oposto da f-string de 600 linhas.

---

## 8. Tratamento de Erros e Testes

- **Lógica de filtro pura e testável:** funções de `filtros.js`/`interacao.js` recebem
  `(registros, filterState)` e devolvem dados, sem tocar no DOM → testáveis em Node com
  asserts simples (sem framework). Casos: "filtro X sobre dataset Y devolve Z linhas";
  "cascata UF→distribuidora esconde opções inválidas"; "URL `#uf=SC` reidrata o estado".
- **Python:** `pytest` sobre `contrato.py` (DataFrame conhecido → JSON esperado) e
  `geo.py` (casos de geocodificação).
- **Erros explícitos:** contrato vazio, aba sem registros, GeoJSON ausente, filtro que
  zera resultados → mensagem clara na UI ("Sem dados para esta seleção") em vez de mapa
  em branco silencioso.
- **Lint/format:** ESLint + Prettier (JS); ruff/black (Python), conforme regras do projeto.

---

## 9. Estratégia de Migração (incremental, baixo risco)

1. **Baseline:** gerar os HTMLs atuais e guardar como referência visual (PNGs em
   `Prints/` auxiliam).
2. **Extrair `comum/`** primeiro (helpers duplicados); os scripts atuais passam a
   importar daí, sem mudar comportamento. Commit verde.
3. **Migrar o dashboard de consumo** para a nova arquitetura, comparando contra o
   baseline até ficar idêntico; então corrigir os bugs de hover/zoom/filtro com o JS já
   testável.
4. **Migrar prospecção** reaproveitando o front pronto.
5. **Só então** aplicar os novos filtros/critérios desejados — agora com segurança.
6. Aposentar os monólitos; atualizar README.

Cada passo é um commit funcional → permite parar/revisar a qualquer momento.

---

## 10. Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Regressão visual durante a migração | Baseline + comparação aba a aba antes de mudar comportamento |
| `file://` bloquear assets | `<script src>` clássico (não módulos ES) + modo de saída único inlined |
| Contrato JSON divergir do que o front espera | Schema versionado (`versao`) + testes pytest no contrato |
| Escopo crescer para confiabilidade de dados | Manter geocodificação/MW explicitamente no Sub-projeto B |

---

## 11. Próximos Passos

1. Revisão deste spec pelo usuário.
2. `writing-plans` → plano de implementação detalhado, fase a fase, derivando o schema
   exato do contrato a partir dos dashboards atuais.
3. Execução incremental conforme a estratégia de migração.

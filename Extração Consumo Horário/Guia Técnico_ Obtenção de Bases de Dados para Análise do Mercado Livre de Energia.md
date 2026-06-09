# Guia Técnico: Obtenção de Bases de Dados para Análise do Mercado Livre de Energia

## 1. Introdução

Este guia técnico detalha os procedimentos para a obtenção de duas bases de dados cruciais para a análise de lacunas e oportunidades no mercado livre de energia: **Dados Empresariais (CNPJs)** e **Consumidores Aptos ao Mercado Livre**. A integração dessas informações com dados de consumo de energia elétrica permite uma visão aprofundada do potencial de mercado em diferentes regiões.

## 2. Obtenção de Dados Empresariais (CNPJs)

Os dados do Cadastro Nacional da Pessoa Jurídica (CNPJ) são disponibilizados pela Receita Federal do Brasil e contêm informações cadastrais de todas as empresas e entidades no país. A principal fonte é a própria Receita Federal, mas existem iniciativas de terceiros que facilitam o acesso e o tratamento desses dados.

### 2.1. Fonte Oficial: Receita Federal do Brasil

*   **Localização**: Os dados abertos do CNPJ são disponibilizados diretamente pela Receita Federal. Embora o link direto possa mudar, a página principal de Dados Abertos da Receita Federal [1] geralmente direciona para a seção correta.
*   **Formato**: Os dados são fornecidos em arquivos compactados (ZIP) contendo múltiplos arquivos CSV. A estrutura é dividida em:
    *   **Estabelecimentos**: Informações sobre cada estabelecimento (filial) de uma empresa, incluindo CNPJ, nome fantasia, endereço completo (com município e UF), CNAE principal e secundário, e situação cadastral.
    *   **Empresas**: Dados da matriz, como razão social, natureza jurídica, capital social.
    *   **Sócios**: Informações sobre os sócios das empresas.
    *   **Simples Nacional**: Dados de empresas optantes pelo Simples Nacional.
*   **Processo de Obtenção**:
    1.  **Acessar a página**: Navegue até a seção de Dados Abertos do CNPJ no site da Receita Federal [1].
    2.  **Download**: Baixe os arquivos ZIP correspondentes aos dados de interesse (geralmente os arquivos de estabelecimentos são os mais relevantes para análise geográfica e setorial).
    3.  **Descompactar**: Os arquivos são grandes e precisam ser descompactados. Recomenda-se o uso de ferramentas de linha de comando (como `unzip` no Linux) ou softwares específicos para lidar com grandes volumes de dados.
    4.  **Tratamento dos Dados**: Os arquivos CSV são extensos e podem exigir tratamento para serem utilizados em análises. Isso inclui:
        *   **Filtragem**: Selecionar apenas as colunas de interesse (CNPJ, município, UF, CNAE, situação cadastral).
        *   **Limpeza**: Remover registros duplicados ou inconsistentes.
        *   **Enriquecimento**: Cruzar informações de diferentes arquivos (ex: unir dados de estabelecimentos com dados de empresas para obter a razão social).
        *   **Indexação**: Criar índices para facilitar buscas e cruzamentos.

### 2.2. Fontes Terceirizadas e Ferramentas Auxiliares

Devido à complexidade e ao volume dos dados da Receita Federal, algumas plataformas e projetos facilitam o acesso e o uso:

*   **Base dos Dados**: A plataforma Base dos Dados [2] oferece uma versão tratada e organizada dos dados do CNPJ, permitindo o download em formatos mais amigáveis ou o acesso via SQL, Python ou R. Isso pode economizar um tempo significativo no tratamento inicial.
*   **Repositórios GitHub**: Existem diversos projetos no GitHub [3] que fornecem scripts e ferramentas para baixar, processar e organizar os dados do CNPJ da Receita Federal. Esses recursos podem ser úteis para automatizar o processo.

### 2.3. Identificação de Clusters Industriais/Comerciais

Após obter e tratar os dados do CNPJ, é possível identificar clusters por município:

1.  **Agregação por Município e CNAE**: Agrupe os estabelecimentos por município e pelo Código Nacional de Atividade Econômica (CNAE). Conte o número de empresas em cada combinação.
2.  **Filtragem por Setor**: Concentre-se nos CNAEs relacionados a setores de alto consumo de energia (indústria, comércio de grande porte, serviços com alta demanda energética).
3.  **Mapeamento Geográfico**: Utilize ferramentas de geoprocessamento para visualizar a concentração de empresas por setor em diferentes municípios, identificando áreas com potencial para o mercado livre.

## 3. Obtenção de Dados de Consumidores Aptos ao Mercado Livre

A identificação de consumidores aptos ao mercado livre é mais complexa, pois não existe um dataset único e direto com essa informação em nível municipal. É necessário inferir o potencial com base nos critérios de elegibilidade e em dados de consumo e unidades consumidoras.

### 3.1. Critérios de Elegibilidade para o Mercado Livre

Atualmente, os principais critérios de elegibilidade para o mercado livre de energia no Brasil são:

*   **Consumidores de Alta Tensão**: Todos os consumidores conectados em alta tensão são elegíveis para o mercado livre.
*   **Consumidores de Baixa Tensão (a partir de 2024)**: A partir de janeiro de 2024, todos os consumidores do Grupo A (alta tensão) e do Grupo B (baixa tensão) podem optar pela compra de energia de qualquer fornecedor, desde que representados por um comercializador varejista [4].

### 3.2. Fontes de Informação e Inferência

*   **CCEE - Mercado Varejista**: O painel do Mercado Varejista da CCEE [5] é uma ferramenta interativa que apresenta dados sobre migrações de consumidores, organizados por agente varejista, distribuidora e Unidade Federativa. Embora não forneça um dataset municipal direto para download, permite analisar o volume de migrações e o perfil dos consumidores que já aderiram, o que pode ser um indicativo do potencial em certas regiões.
*   **Dados de Unidades Consumidoras (ANEEL)**: A ANEEL disponibiliza dados sobre unidades consumidoras, mas a obtenção de um dataset com granularidade municipal e informações detalhadas de consumo por unidade consumidora é desafiadora. Conforme pesquisa anterior, o dataset de "unidades consumidoras por município" não foi encontrado no portal de dados abertos da ANEEL [6]. No entanto, relatórios e painéis interativos da ANEEL sobre distribuição [7] podem conter informações agregadas que auxiliem na inferência.
*   **Dados de Consumo por Classe (EPE)**: O dataset de Consumo Mensal de Energia Elétrica por Classe da EPE [8] fornece o consumo por classe (industrial, comercial, residencial) em níveis regional e por subsistema. Embora não seja municipal, pode ser usado para identificar regiões com alto consumo industrial/comercial, que são os principais alvos do mercado livre.

### 3.3. Estratégia de Inferência de Consumidores Aptos por Município

Dado a dificuldade de obter um dataset direto, a estratégia para identificar consumidores aptos por município envolve o cruzamento e a inferência a partir de outras bases:

1.  **Utilizar Dados de CNPJs**: Filtre os dados de CNPJs por setores de atividade econômica que tipicamente possuem alto consumo de energia (indústrias, grandes comércios, hospitais, etc.).
2.  **Estimativa de Consumo**: Para cada empresa identificada, pode-se estimar o consumo de energia com base no seu porte (capital social, número de funcionários, se disponível) e no consumo médio do seu setor de atividade. Isso pode ser feito através de benchmarks setoriais ou estudos de caso.
3.  **Critério de Demanda**: Com base na estimativa de consumo, identifique as empresas que provavelmente possuem demanda contratada superior aos limites de elegibilidade para o mercado livre (historicamente, 500 kW ou 300 kW, e agora todos os consumidores de alta e baixa tensão).
4.  **Localização Geográfica**: Agregue essas empresas por município para ter uma estimativa do número de consumidores aptos por localidade.
5.  **Cruzamento com Migrações (CCEE)**: Compare a estimativa de consumidores aptos com os dados de migrações da CCEE (por UF ou distribuidora, se disponível) para identificar municípios com alto potencial não explorado.

## 4. Desafios e Considerações

*   **Volume de Dados**: Os dados do CNPJ são extremamente volumosos e exigem capacidade de processamento e armazenamento.
*   **Qualidade dos Dados**: A Receita Federal realiza atualizações periódicas, mas a qualidade e a completude dos dados podem variar. É fundamental realizar etapas de limpeza e validação.
*   **Inferência vs. Dados Diretos**: A identificação de consumidores aptos é, em grande parte, um processo de inferência. Os resultados devem ser tratados como estimativas e validados com informações de mercado sempre que possível.
*   **Privacidade**: Ao lidar com dados de empresas, é importante estar atento às leis de proteção de dados e utilizar apenas informações públicas e agregadas para análises de mercado.

## 5. Conclusão

A obtenção e o tratamento das bases de dados de CNPJs e a inferência de consumidores aptos ao mercado livre são etapas fundamentais para uma análise estratégica do setor de energia. Embora apresentem desafios técnicos e de volume de dados, as informações resultantes permitem identificar com precisão lacunas de mercado, direcionar esforços de prospecção e desenvolver estratégias de negócio mais eficazes no cenário de abertura do mercado livre de energia.

## 6. Referências

[1] Receita Federal do Brasil. **Dados Abertos CNPJ**. Disponível em: [https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros).
[2] Base dos Dados. **Diretórios Brasileiros - CNPJ**. Disponível em: [https://basedosdados.org/dataset/33b49786-fb5f-496f-bb7c-9811c985af8e?table=b71e9a46-f98e-476b-a2d6-4444213a8ddc](https://basedosdados.org/dataset/33b49786-fb5f-496f-bb7c-9811c985af8e?table=b71e9a46-f98e-476b-a2d6-4444213a8ddc).
[3] GitHub. **aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ**. Disponível em: [https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ/](https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ/).
[4] CCEE. **CCEE finaliza primeira parte do estudo com propostas para abertura total do mercado livre de energia**. Disponível em: [https://www.ccee.org.br/-/ccee-finaliza-primeira-parte-do-estudo-com-propostas-para-abertura-total-do-mercado-livre-de-energia](https://www.ccee.org.br/-/ccee-finaliza-primeira-parte-do-estudo-com-propostas-para-abertura-total-do-mercado-livre-de-energia).
[5] CCEE. **Mercado Varejista**. Disponível em: [https://www.ccee.org.br/mercado-varejista](https://www.ccee.org.br/mercado-varejista).
[6] ANEEL. **Portal de Dados Abertos**. Disponível em: [https://dadosabertos.aneel.gov.br/dataset/](https://dadosabertos.aneel.gov.br/dataset/).
[7] ANEEL. **Distribuição - Relatórios e Indicadores**. Disponível em: [https://www.gov.br/aneel/pt-br/centrais-de-conteudos/relatorios-e-indicadores/distribuicao](https://www.gov.br/aneel/pt-br/centrais-de-conteudos/relatorios-e-indicadores/distribuicao).
[8] EPE. **Consumo Mensal de Energia Elétrica por Classe (regiões e subsistemas)**. Disponível em: [https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes/consumo-de-energia-eletrica](https://www.epe.gov.br/pt/publicacoes-dados-abertos/publicacoes/consumo-de-energia-eletrica).

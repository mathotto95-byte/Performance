# Performance

Performance OTS e OTD, com o sistema Regras Estadia integrado.

Sistema Streamlit independente para importar **Resultados da OTS e OTD** e **Resultados Estadia**.

Segue a identidade visual dos sistemas OTS/OTD e Estadias: fundo escuro, menu azul-marinho, detalhes dourados, indicadores e tabelas com bordas arredondadas.

## Configuração no Streamlit Community Cloud

- Branch: `main`
- Main file path: `app.py`
- Python: `3.12`

O tema fica em `.streamlit/config.toml` e `theme.py`.

## Executar

Na pasta deste sistema:

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Uso

1. Exporte os resultados em Excel no sistema de origem.
2. Em Importações, selecione a base de destino e o arquivo `.xlsx` ou `.xls`.
3. Selecione a aba e a linha do cabeçalho, confira a prévia e clique em Importar resultados.
4. Consulte versões anteriores, pesquise registros e exporte a consulta em Excel.

Cada importação é uma versão completa, preservada no banco SQLite próprio em `data/regras_estadia.sqlite3`. Conteúdo idêntico na mesma fonte não é duplicado. Nenhum banco dos sistemas de origem é alterado. Faça cópias desse arquivo para backup; armazenamento local de hospedagens temporárias pode não persistir.

As colunas de origem são preservadas. A aba sugerida para OTS/OTD é `ots_otd`; para Estadia, `resultado_completo`, `resultado` ou `completo`, quando disponível. A seleção pode ser ajustada na tela.

Esta primeira etapa contempla importação e consulta. Chaves de relacionamento, validações de negócio, franquias e cálculos ainda dependem da definição das regras. Não há cruzamento automático ou cálculo de cobrança nesta versão. O aplicativo é local e ainda não possui autenticação.

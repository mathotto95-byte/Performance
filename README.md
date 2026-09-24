# Performance

Performance OTS e OTD, com o sistema Regras Estadia integrado.

Sistema Streamlit independente para importar **Resultados da OTS e OTD** e **Resultados Estadia**.

Segue a identidade visual dos sistemas OTS/OTD e Estadias: fundo escuro, menu azul-marinho, detalhes dourados, indicadores e tabelas com bordas arredondadas.

## Configuração no Streamlit Community Cloud

- Branch: `main`
- Main file path: `app.py`
- Python: `3.12`

O tema fica em `.streamlit/config.toml` e `theme.py`.

## Sincronização do Banco OTS e OTD

Em Secrets do **Performance**, acrescente uma seção independente (mantenha os blocos de login):

```toml
[ots_sync]
token = "SEU_TOKEN_GITHUB_COM_LEITURA_DO_OTSeOTD"
branch = "main"
```

O token precisa de Contents: Read no repositório `mathotto95-byte/OTSeOTD`. Também aceita `GITHUB_TOKEN` na raiz dos Secrets ou `[github].token`, caso já configurado. Não coloque tokens neste repositório.

No menu **Sincronização OTS e OTD**, clique em **Sincronizar resultados**. A origem é `backups/ots_otd_latest.json`, publicado pelo aplicativo `https://ontimeshipdev.streamlit.app/`. A tela informa a data do backup e da sincronização. ADMIN e OPERACIONAL podem sincronizar; CONSULTA pode consultar os resultados recebidos.

Os dados reproduzem as onze colunas do **Banco OTS e OTD**, incluindo registros originais e alterações, sem limite de 500 linhas. A sincronização é manual e recebe a última versão publicada no GitHub, não lê diretamente a sessão do Streamlit nem o banco Supabase. Atualize o backup no sistema de origem para disponibilizar mudanças recentes. Backups inválidos ou vazios não substituem a base atual; versões anteriores ficam no histórico. NSDocs, LCTE e Estadias ainda não têm sincronização implementada.

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

Esta primeira etapa contempla importação e consulta. Chaves de relacionamento, validações de negócio, franquias e cálculos ainda dependem da definição das regras. Não há cruzamento automático ou cálculo de cobrança nesta versão.

## Login

O acesso exige usuário ou e-mail e senha, no mesmo formato de Secrets do Controle Integrado. Configure em Settings > Secrets do aplicativo Performance no Streamlit:

```toml
[auth.admin]
username = "admin"
name = "Administrador"
email = "admin@empresa.com"
password = "SUBSTITUA_POR_SUA_SENHA"
role = "ADMIN"

[auth.users.operador]
username = "operador"
name = "Operador"
password = "SUBSTITUA_POR_OUTRA_SENHA"
role = "OPERACIONAL"
```

Também aceita `password_hash` no formato PBKDF2-SHA256 ou bcrypt, e as variáveis `AUTH_ADMIN_PASSWORD` / `AUTH_USERS_JSON` do Controle Integrado. Não existe senha padrão. Credenciais e usuários do banco do Controle Integrado não são copiados automaticamente; configure os acessos neste aplicativo. Não publique senhas no GitHub.

ADMIN e OPERACIONAL podem importar. CONSULTA acessa visualização, histórico e exportação. Há bloqueio de cinco minutos após cinco falhas na sessão, expiração após 60 minutos de inatividade (verificada na próxima interação), botão Sair e registro de eventos de acesso no banco próprio. O bloqueio de tentativas segue o Controle Integrado e é limitado à sessão do navegador.

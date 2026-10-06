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

Os dados reproduzem as onze colunas do **Banco OTS e OTD**, incluindo registros originais e alterações, sem limite de 500 linhas. A sincronização é manual e recebe a última versão publicada no GitHub, não lê diretamente a sessão do Streamlit nem o banco Supabase. Atualize o backup no sistema de origem para disponibilizar mudanças recentes. Backups inválidos ou vazios não substituem a base atual; versões anteriores ficam no histórico.

## Testar a análise Performance

1. Sincronize OTS/OTD e **Estadias** pelos menus correspondentes. O token existente precisa ter leitura também no repositório `mathotto95-byte/Estadias`. Alternativamente, configure `[estadias_sync]` com `token = "SEU_TOKEN"`.
2. A sincronização Estadias recebe também o **LCTE / Observação** do backup completo existente, sem reenviar a planilha. Reutiliza a Observação original e o monitoramento já armazenados. Caso o backup só contenha resultados, publique um backup completo no Estadias e sincronize novamente; a importação manual em **Importações → LCTE / Observação** continua disponível.
3. Abra **Análise Performance**, confira as versões das três bases e exporte a análise se necessário.

A extração usa números isolados de sete dígitos na Observação. Múltiplos códigos ou associações conflitantes ficam sem classificação. Monitoramento liga os agendamentos; NF + placa liga as chegadas já calculadas no Estadias. Os backups simples e completos do Estadias são aceitos. A análise não recalcula rastreador nem altera bancos de origem. NSDocs ainda não está integrado.

OTS 2 compara agendamento de carga com previsão. OTS 3 compara chegada na origem com agendamento, usando previsão quando o agendamento está vazio. OTD 2 compara Agenda GFL com Data Limite. OTD 3 compara chegada no destino com Agenda GFL, usando Data Limite quando Agenda GFL está vazia. A igualdade é Dentro do prazo. Limites sem horário são comparados por dia; eventos sem horário no mesmo dia de um limite com hora ficam Sem informação. A análise usa o último registro OTS/OTD de cada monitoramento na versão selecionada.

OTD 1 permanece Sem informação: o histórico OTS não comprova o momento real de realização do agendamento. A emissão da NF é extraída exclusivamente de Data Emissão NF, nunca da emissão do CT-e. A tabela apresenta o motivo de cada classificação; registros sem chave única não são associados por aproximação.

Quando a Data Limite do OTD cai no domingo, segunda-feira é aceita até o fim do dia. No resumo OTD, tanto domingo quanto segunda são OK; datas anteriores permanecem Antecipado e terça em diante é Atrasado. A tolerância também é aplicada à OTD 2 e à OTD 3 quando esta usa a Data Limite por ausência de Agenda GFL. O mês de vigência é definido pela Previsão de Carga, inclusive quando a tolerância avança para o mês seguinte.

Exceção OTD por chegada: um agendamento atrasado é considerado atendido quando a chegada no destino do rastreador está dentro do limite, incluindo a tolerância de domingo. Não depende de uma marcação de falta de grade. Chegada ausente, conflitante ou tardia mantém o atraso. A análise registra a exceção em coluna própria e no motivo, preservando a Agenda GFL original. O resumo OTD usa essa exceção apenas quando todas as NFs vinculadas ao monitoramento a atendem; sem LCTE/Estadias, continua considerando o agendamento original.

Chegadas do rastreador podem ser recuperadas de duplicações com a mesma NF + placa e a mesma `chave_viagem` preenchida, desde que não haja divergências de origem, destino, emissão da NF, monitoramento ou horários. Campos vazios são complementados pelos horários existentes. Esses registros recebem a indicação de viagem duplicada compatível para a validação manual; continuam sem aprovação financeira ou vínculo automático de retorno no Estadias até resolver a duplicidade na origem.

## Indicadores, painel e retorno ao Estadias

Na Visão geral, **OTD atrasado — análise manual** lista os atrasos pelo agendamento original, mesmo após aprovação, com os campos do Banco OTS/OTD e NF/placa/chegada/correspondência do rastreador. Segue o filtro de mês de vigência da Previsão de Carga. ADMIN e OPERACIONAL podem preencher **Justificativa**, marcar **Dentro da regra** e salvar. Cada decisão vale para o monitoramento mostrado e suas NFs vinculadas. CONSULTA só visualiza e exporta.

A lista manual busca diretamente `monitoramento` nos resultados do Estadias, mesmo sem vínculo no LCTE. Exibe NF, placa, origem, destino, chegadas e identificação do registro em colunas separadas; quando existem vários registros, as linhas dentro das células mantêm a mesma ordem para conferência. O vínculo exato por código não escolhe automaticamente uma viagem entre candidatos: a validação abrange o conjunto exibido. O cruzamento das regras por NF + placa permanece preservado.

A aprovação muda o card OTD para OK e o OTD 2 analisável para Dentro do prazo; não libera as demais regras. O resultado automático, o autor, a data e a justificativa permanecem disponíveis. Desmarcar a flag e salvar com justificativa restaura o cálculo automático. Alterações nos dados OTS ou nas NFs/chegadas vinculadas exigem nova validação. A lista inclui um card específico de validações manuais.

As decisões ficam na tabela `otd_validacoes` do SQLite já utilizado pelo Performance, com histórico de alterações, sem alterar importações ou bancos de origem. Esse arquivo deve ser incluído no backup: assim como as importações locais, não tem persistência garantida após recriação da instância no Streamlit Cloud. A exportação da lista permite consultar as decisões fora do aplicativo. A publicação habitual para Estadias inclui os resultados efetivos e seus motivos.

Na **Visão geral**, os cards **Agendamentos — somente Banco OTS e OTD** independem do LCTE e do Estadias. Usam o último registro por monitoramento: OTS compara Agendamento Carga com Previsão Carga; OTD compara Agenda GFL com Data Limite. Mesmo dia = OK, antes = Antecipado, depois = Atrasado. Horários não alteram essa classificação. Cada status tem quantidade e percentual sobre os registros analisáveis; datas ausentes/inválidas ficam Sem informação. O filtro Mês de vigência — Previsão de Carga usa a Previsão de Carga tanto no OTS quanto no OTD e na lista de análise manual. Todos exibe a base completa; Sem data reúne referências ausentes ou inválidas. Esse filtro é independente do mês de emissão da NF aplicado às cinco regras de estadia.

O filtro **Mês de emissão da NF** limita os indicadores, listas e exportações da tela. A lista **Válidas para validação manual — OTS 2 e OTD 2** inclui NFs com ambas as regras dentro do prazo, mantendo visíveis as pendências das demais regras e de correspondência no Estadias. A inclusão nessa lista não aprova a viagem nem confirma cobrança de estadia. A publicação para Estadias continua abrangendo a base completa, independentemente do filtro de mês.

Em **Análise Performance**, os percentuais usam somente Dentro + Fora. O total de NFs conta pares únicos de NF + placa; chaves ausentes não entram nos indicadores. **Atendeu todas as regras** é Não quando existe atraso, Sim quando todas as cinco regras têm informação e estão dentro, e Sem informação nos demais casos. Não há dispensas de regras presumidas.

O **Painel de Controle** reutiliza os períodos por origem/destino e o identificador do registro Estadias. Início é chegada + franquia; fim é saída. Horas são calculadas sem arredondamento para inteiro e Valor é horas × R$ 68,00, arredondado somente para centavos. Totais financeiros contam cada período uma única vez, mesmo com várias notas. Tarefa fica vazia quando não há campo de tarefa na origem. Envio usa `analise_enviada_em`; Prazo é Envio + 15 dias corridos. Prazo vencido considera a data atual em São Paulo, sem vencer antecipadamente no próprio dia.

O painel e sua exportação incluem **Previsão de Carga**, **Agendamento de Carga**, **Data Limite**, **Agenda GFL** e **Dentro da Regra**, além da classificação individual das cinco regras, reaproveitando a análise vigente.

## Backup diário às 20h

O menu **Backup** mostra a situação do agendamento e permite **Fazer backup agora**. O banco SQLite completo, incluindo importações, sincronizações, validações OTD e histórico, é copiado com a API de backup do SQLite e verificado antes do envio. Secrets, senhas e tokens de configuração não estão no banco e não são incluídos.

Destino privado: `mathotto95-byte/Performance-backups`, branch `main`. Mantém dois arquivos fixos: `backups/performance_1.zip` e `backups/performance_2.zip`. Na primeira execução há uma cópia; na seguinte, duas; depois cada envio substitui a mais antiga. O histórico de commits do GitHub não é apagado. Cada ZIP inclui o banco `regras_estadia.sqlite3` e um manifesto com data/hora e SHA-256. Para recuperação, extraia o banco e substitua o arquivo local com o aplicativo parado.

O token já usado em `performance_publish.token` ou na sincronização OTS é reutilizado se possuir **Contents: Read and write** no repositório privado. Se for restrito a repositórios selecionados, inclua `Performance-backups` entre eles. Alternativamente:

```toml
[performance_backup]
token = "SEU_TOKEN_COM_ESCRITA_NO_REPOSITORIO_PRIVADO"
repository = "mathotto95-byte/Performance-backups"
branch = "main"
```

O agendador inicia ao acessar o Performance autenticado e continua no processo do servidor às **20h de Brasília**. Se o Streamlit estiver suspenso, verifica o backup pendente quando o aplicativo voltar e copia os dados então disponíveis; não reconstrói dados perdidos durante a suspensão. Falhas de rede/permissão têm nova tentativa a cada 15 minutos. Banco vazio ou inválido nunca substitui as cópias anteriores, e o envio é bloqueado para repositório público. O backup não depende de manter o computador do usuário ligado.

O Estadias publica os envios nos próximos backups, sem mudar tabelas. Sincronize novamente depois desse backup. Por padrão, sua sincronização usa a branch `backup-data`; para outro destino, configure `branch` em `[estadias_sync]`.

Para devolver o resultado, em Análise Performance clique **Publicar resultado para Estadias**. O arquivo `backups/performance_latest.json` é gravado na branch main do Performance com data da análise, motivos e identificação das bases. Configure um token com Contents: Read and write no repositório Performance:

```toml
[performance_publish]
token = "SEU_TOKEN_COM_ESCRITA_NO_PERFORMANCE"
```

O token de OTS é usado como alternativa, se já possuir essa permissão. CONSULTA não pode publicar. A publicação é manual e abrange a análise completa das versões selecionadas. No Estadias, abra **PerformanceRW → Atualizar resultado**. Os dois sistemas não precisam compartilhar banco. Resultados com chave ambígua ou horários de chegada diferentes dos atuais não são vinculados. As regras são calculadas apenas no Performance.

## Executar localmente

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

O sistema contempla importação, consulta e análise de pontualidade por NF + placa, conforme as regras descritas acima. Não calcula cobrança de estadia.

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


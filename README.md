
# 4Yousee Monitoramento 24/7 (Cloud Run + Discord/Telegram)

Este projeto transforma a API da 4Yousee em um sistema de monitoramento profissional 24 horas por dia, 7 dias por semana, usando o Google Cloud Run para automação e o Cloud Scheduler para agendamento.

## 🚀 Funcionalidades

O sistema opera em dois modos distintos, acionados por agendamentos diferentes:

| **Modo de Execução**       	| **Agendamento**                                 	| **Comportamento**                                                                                                            	|
|----------------------------	|-------------------------------------------------	|------------------------------------------------------------------------------------------------------------------------------	|
| **DELTA**(?mode=delta)     	| A cada 10 minutos<br>(*/10 * * * *)             	| **ALERTA RÁPIDO.** Verifica mudanças de status.<br>**Notifica SOMENTE se houver alteração** (silêncio total caso contrário). 	|
| **SUMMARY**(?mode=summary) 	| Horários fixos <br>(0, 7, 10, 13, 16, 20 * * *) 	| **RELATÓRIO GERAL.** Envia o status <br>completo de **todos** os Players (ID, Nome, Status, Último Contato).                 	|

## ⚙️ Setup de Infraestrutura (Google Cloud)

### 1. Pré-requisitos

1.  Uma conta Google Cloud (GCP) com faturamento ativado.
    
2.  A ferramenta gcloud (Google Cloud CLI) instalada.
    
3.  Permissões de Cloud Build Editor e Cloud Run Invoker no seu projeto.
    
4.  Cópia dos arquivos app.py, requirements.txt, e Dockerfile.
    

### 2. Configuração de Variáveis de Ambiente

Todas as credenciais sensíveis devem ser injetadas de forma segura. O seu código (app.py) depende delas.

| **Modo de Execução**       	| **Agendamento**                                 	| **Comportamento**                                                                                                            	|
|----------------------------	|-------------------------------------------------	|------------------------------------------------------------------------------------------------------------------------------	|
| **DELTA**(?mode=delta)     	| A cada 10 minutos<br>(*/10 * * * *)             	| **ALERTA RÁPIDO.** Verifica mudanças de status.<br>**Notifica SOMENTE se houver alteração** (silêncio total caso contrário). 	|
| **SUMMARY**(?mode=summary) 	| Horários fixos <br>(0, 7, 10, 13, 16, 20 * * *) 	| **RELATÓRIO GERAL.** Envia o status <br>completo de **todos** os Players (ID, Nome, Status, Último Contato).                 	|

### 3. Implantação no Cloud Run (Via Cloud Shell)

Execute estes comandos no Cloud Shell, substituindo [SEU_ID_DO_PROJETO] pelo ID do seu GCP.

#### A. Definir o Projeto (Se necessário)

gcloud config set project [SEU_ID_DO_PROJETO]

  

#### B. Construir a Imagem Docker

gcloud builds submit --tag gcr.io/[SEU_ID_DO_PROJETO]/monitor-4yousee

  

#### C. Implantar o Serviço (Injetando Variáveis)

ATENÇÃO: Substitua os valores entre aspas pelos seus segredos reais.

gcloud run deploy monitor-4yousee \

--image gcr.io/[SEU_ID_DO_PROJETO]/monitor-4yousee \

--platform managed \

--region us-central1 \

--allow-unauthenticated \

--min-instances 0 \

--max-instances 1 \

--set-env-vars API_TOKEN="SEU_TOKEN",TELEGRAM_TOKEN="SEU_TOKEN_TELEGRAM",TELEGRAM_CHAT_ID="SEU_CHAT_ID",DISCORD_WEBHOOK_URL="SUA_URL_DO_DISCORD"

  

Guarde a URL do Serviço que este comando retornar.

### 4. Configuração do Cloud Scheduler

Crie os dois Jobs de agendamento usando a URL do Serviço que você acabou de obter.

#### Job 1: Alerta Rápido (DELTA)

-   Frequência:  */10 * * * * (A cada 10 minutos)
    
-   URL:  [SUA_URL_DO_CLOUD_RUN]/?mode=delta
    

#### Job 2: Resumo Geral (SUMMARY)

-   Frequência:  0 7,10,13,16,20 * * * (Horários fixos)
    
-   URL:  [SUA_URL_DO_CLOUD_RUN]/?mode=summary
  

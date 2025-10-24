import requests
import json
from datetime import datetime
import asyncio
from telegram import Bot
from telegram.error import TelegramError
import os
from flask import Flask, jsonify, request
import pytz 

# --- CONFIGURAÇÕES DO FLASK ---
app = Flask(__name__)

# --- CONSTANTES DE MODO ---
MODE_DELTA = "delta"    # Monitoramento de 10 em 10 minutos (Notifica SOMENTE mudanças)
MODE_SUMMARY = "summary" # Monitoramento agendado (Notifica TODOS os players)

# --- CONFIGURAÇÕES GERAIS ---
LOCAL_TIMEZONE = "America/Sao_Paulo" # Fuso horário de Brasília/São Paulo

# --- CONFIGURAÇÕES DA API 4YOUSEE (SANITIZADO) ---
API_BASE_URL = "https://api.4yousee.com.br"
# Segredo injetado pelo Cloud Run. Fallback é string vazia para segurança.
API_TOKEN = os.environ.get("API_TOKEN", "") 

# --- CONFIGURAÇÕES DO TELEGRAM (SANITIZADO) ---
TELEGRAM_ENABLED = True
# Segredos injetados pelo Cloud Run. Fallbacks são strings vazias.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- CONFIGURAÇÕES DO DISCORD (SANITIZADO) ---
DISCORD_ENABLED = True
# Segredo injetado pelo Cloud Run. Fallback é string vazia.
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "") 

# --- ARQUIVOS (Cloud Run usa /tmp) ---
STATUS_FILE = '/tmp/player_status_anterior.json' 

# --- HEADERS PARA API ---
HEADERS = {
    'Secret-Token': API_TOKEN,
    'Content-Type': 'application/json'
}

# --- FUNÇÃO PRINCIPAL (@app.route) ---

@app.route("/", methods=["GET"])
def run_monitoramento():
    """Endpoint chamado pelo Cloud Scheduler para iniciar a varredura."""
    
    mode = request.args.get('mode', MODE_DELTA) 
    
    local_now = datetime.now(pytz.timezone(LOCAL_TIMEZONE))
    local_time_str = local_now.strftime('%d/%m/%Y %H:%M:%S')

    print(f"--- INICIANDO EXECUÇÃO ({mode.upper()}) VIA HTTP TRIGGER ---")
    
    players_data = obter_players_via_api()

    if players_data is None:
        return jsonify({"status": "error", "message": "Falha ao obter dados da API."}), 500
    
    if mode == MODE_SUMMARY:
        executar_monitoramento_resumo(players_data, local_time_str)
    
    elif mode == MODE_DELTA:
        executar_monitoramento_delta(players_data, local_time_str)

    print("--- EXECUÇÃO CONCLUÍDA ---")
    return jsonify({"status": "success", "message": f"Monitoramento {mode.upper()} executado."}), 200

# --- EXECUTORES DE MODO ---

def executar_monitoramento_delta(players_data, local_time_str):
    """
    Compara o status, notifica SOMENTE se houver mudanças (Alerta) e salva o novo status.
    Silêncio total se não houver mudança. (Usado para o agendamento de 10 em 10 minutos).
    """
    print("Modo Delta: Iniciando comparação de status.")
    
    mudancas = comparar_e_salvar_status(players_data) # Salva o status aqui

    if mudancas:
        print(f"📢 Alerta Delta: {len(mudancas)} mudança(s) detectada(s). Enviando alerta.")
        
        # Ordem de Notificação: Discord primeiro
        if DISCORD_ENABLED:
            enviar_notificacao_alerta_discord(mudancas, local_time_str)
        if TELEGRAM_ENABLED:
            enviar_notificacao_alerta_telegram(mudancas, local_time_str)
    else:
        # Permanece em silêncio se não houver mudança.
        print("✅ Nenhuma mudança de status detectada. Mantendo monitoramento silencioso.")
        
def executar_monitoramento_resumo(players_data, local_time_str):
    """
    Envia o status completo de TODOS os players. (Usado para os agendamentos de horário fixo).
    """
    print("Modo Resumo: Enviando status geral de todos os players.")
    
    # Ordem de Notificação: Discord primeiro
    if DISCORD_ENABLED:
        enviar_notificacao_resumo_discord(players_data, local_time_str)
    if TELEGRAM_ENABLED:
        enviar_notificacao_resumo_telegram(players_data, local_time_str)
    
# --- FUNÇÕES CORE (Comparação/Persistência) ---

def comparar_e_salvar_status(current_players_data):
    """Compara o status atual com o anterior e salva o novo status. Retorna as mudanças."""
    
    status_anterior = carregar_status_anterior()
    mudancas = []
    current_players_map = {p['nome']: p for p in current_players_data}
    
    print("\nComparando status...")

    for player_name, player_data in current_players_map.items():
        current_status = player_data['status']
        previous_status = status_anterior.get(player_name)
        player_id = player_data['id']
        
        if previous_status != current_status:
            mudanca_info = {
                'id': player_id,
                'nome': player_name,
                'anterior': previous_status or "NOVO",
                'atual': current_status,
                'tempo': player_data['ultimo_contato']
            }
            mudancas.append(mudanca_info)
            print(f"   🚨 MUDANÇA: [{player_id}] - {player_name}: {previous_status or 'NOVO'} → {current_status}")

    # Salvar o status atual
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_players_data, f, indent=4, ensure_ascii=False)
        print(f"\n💾 Status atual salvo em '{STATUS_FILE}'.")
    except Exception as e:
        print(f"❌ Erro ao salvar status: {e}")
        
    return mudancas

def carregar_status_anterior():
    """Carrega o status anterior dos players de um arquivo JSON."""
    try:
        if not os.path.exists(STATUS_FILE):
             return {}
             
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            dados = json.load(f)
            return {p['nome']: p['status'] for p in dados}
            
    except json.JSONDecodeError:
        print("   ⚠️ Erro ao ler JSON. O arquivo de status será ignorado.")
        return {}
    except Exception as e:
        print(f"   ⚠️ Erro ao carregar status anterior: {e}")
        return {}

# --- FUNÇÕES AUXILIARES ---

def obter_players_via_api():
    """Busca todos os players usando a API do 4YouSee."""
    
    print("\n1. Buscando players via API...")
    
    if not API_TOKEN:
        print("❌ Token da API não configurado!")
        return None
    
    try:
        url = f"{API_BASE_URL}/v1/players" 
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            players = data.get('results', [])
            
            players_processados = processar_dados_players(players)
            print(f"✅ {len(players_processados)} players obtidos via API.")
            return players_processados
            
        else:
            print(f"❌ Erro HTTP {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro de requisição ao buscar players: {e}")
        return None
        
    except Exception as e:
        print(f"❌ Erro geral ao buscar players: {e}")
        return None

def processar_dados_players(players):
    """Processa os dados retornados pela API para o formato padronizado."""
    players_processados = []
    for player in players:
        player_id = player.get('id', '')
        nome = player.get('name', 'Nome Não Encontrado')
        player_status = player.get('playerStatus', {})
        status = player_status.get('name', 'Status Não Encontrado')
        last_contact_min = player.get('lastContactInMinutes')
        
        # Lógica para formatação do último contato
        if last_contact_min is None:
            ultimo_contato = "Nunca acessado"
        elif last_contact_min == 0:
            ultimo_contato = "Agora"
        elif last_contact_min < 60:
            ultimo_contato = f"há {last_contact_min} minuto(s)"
        elif last_contact_min < 1440:
            horas = last_contact_min // 60
            ultimo_contato = f"há {horas} hora(s)"
        else:
            dias = last_contact_min // 1440
            ultimo_contato = f"há {dias} dia(s)"
        
        players_processados.append({
            'id': player_id, 'nome': nome, 'status': status,
            'ultimo_contato': ultimo_contato, 'ultimo_contato_minutos': last_contact_min
        })
    return players_processados

# --- FUNÇÕES DE NOTIFICAÇÃO DELTA (USADAS PELO MODE_DELTA) ---

async def enviar_mensagem_alerta_async(mudancas, local_time_str):
    """Envia alerta de mudanças via Telegram."""
    bot = Bot(token=TELEGRAM_TOKEN)
    
    try:
        # ALERTA DE MUDANÇAS
        mensagem = "🚨 *Alerta de Mudança de Status*\n"
        mensagem += f"⏰ {local_time_str}\n\n"
        
        for m in mudancas:
            status_lower = m['atual'].lower()
            emoji = "✅" if 'online' in status_lower else "❌" if 'offline' in status_lower else "⚠️"
            
            mensagem += f"{emoji} *[{m['id']}] {m['nome']}* \n"
            mensagem += f"   Status: {m['anterior']} → {m['atual']}\n"
            mensagem += f"   🕐 Último Contato: {m['tempo']}\n\n"
        
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensagem, parse_mode='Markdown')
        print("✅ Notificação Alerta enviada com sucesso pelo Telegram!")
        
    except TelegramError as e:
        print(f"❌ Erro do Telegram (Alerta): {e}")

def enviar_notificacao_alerta_telegram(mudancas, local_time_str):
    """Wrapper síncrono para alerta de mudanças."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        import asyncio
        asyncio.run(enviar_mensagem_alerta_async(mudancas, local_time_str))
    except Exception as e:
        print(f"❌ Erro ao executar envio Alerta assíncrono: {e}")


def enviar_notificacao_alerta_discord(mudancas, local_time_str):
    """Envia alerta de mudanças via Webhook do Discord."""
    if not DISCORD_WEBHOOK_URL: return

    try:
        title = "🚨 Alerta de Mudança de Status"
        color = 16711680 # Vermelho para alerta

        fields = []
        for m in mudancas:
            status_lower = m['atual'].lower()
            emoji = "✅" if 'online' in status_lower else "❌" if 'offline' in status_lower else "⚠️"
            
            field_value = (
                f"**De:** {m['anterior']}\n"
                f"**Para:** **{m['atual']}**\n"
                f"**Último Contato:** {m['tempo']}"
            )
            
            fields.append({"name": f"{emoji} ID:[{m['id']}] - {m['nome']}", "value": field_value, "inline": False})
        
        description = f"⏰ **Varredura:** {local_time_str}\nTotal de mudanças: {len(mudancas)}"

        embed = {"title": title, "description": description, "color": color, "fields": fields}
        payload = {"embeds": [embed]}

        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status() 

        print("✅ Notificação Alerta enviada com sucesso pelo Discord!")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao enviar notificação Alerta para Discord. Verifique a URL do Webhook: {e}")
    except Exception as e:
        print(f"❌ Erro desconhecido ao enviar notificação Alerta para Discord: {e}")


# --- FUNÇÕES DE NOTIFICAÇÃO RESUMO (USADAS PELO MODE_SUMMARY) ---

async def enviar_mensagem_resumo_async(players_data, local_time_str):
    """Envia relatório geral de todos os players via Telegram."""
    bot = Bot(token=TELEGRAM_TOKEN)
    
    try:
        mensagem = "📊 *Relatório de Status Geral*\n"
        mensagem += f"⏰ {local_time_str}\n\n"
        
        for player in players_data:
            status_lower = player['status'].lower()
            emoji = "✅" if 'online' in status_lower else "❌" if 'offline' in status_lower else "⚠️"
            
            mensagem += f"\n{emoji} *[{player['id']}] {player['nome']}* - "
            mensagem += f"Status: {player['status']}\n"
            mensagem += f"  Último Contato: {player['ultimo_contato']}\n"
            
        mensagem += f"\n📊 Total de Players: {len(players_data)}"
        
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensagem, parse_mode='Markdown')
        print("✅ Notificação Resumo enviada com sucesso pelo Telegram!")
        
    except TelegramError as e:
        print(f"❌ Erro do Telegram (Resumo): {e}")

def enviar_notificacao_resumo_telegram(players_data, local_time_str):
    """Wrapper síncrono para relatório geral."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        import asyncio
        asyncio.run(enviar_mensagem_resumo_async(players_data, local_time_str))
    except Exception as e:
        print(f"❌ Erro ao executar envio Resumo assíncrono: {e}")


def enviar_notificacao_resumo_discord(players_data, local_time_str):
    """Envia relatório geral de todos os players via Webhook do Discord."""
    if not DISCORD_WEBHOOK_URL: return

    try:
        title = "📊 Relatório de Status Geral"
        color = 3066993 # Verde/Sucesso

        fields = []
        for player in players_data:
            status_lower = player['status'].lower()
            emoji = "✅" if 'online' in status_lower else "❌" if 'offline' in status_lower else "⚠️"
            
            field_value = (
                f"Status: **{player['status']}**\n"
                f"Último Contato: {player['ultimo_contato']}"
            )
            
            fields.append({"name": f"{emoji} ID:[{player['id']}] - {player['nome']}", "value": field_value, "inline": True})
        
        if len(fields) > 25:
            fields = fields[:24] 
            fields.append({"name": "...", "value": f"E mais {len(players_data) - 24} players.", "inline": False})

        embed = {"title": title, "description": f"⏰ **Varredura:** {local_time_str}\nTotal de Players: **{len(players_data)}**", "color": color, "fields": fields}
        payload = {"embeds": [embed]}

        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status() 

        print("✅ Notificação Resumo enviada com sucesso pelo Discord!")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao enviar notificação Resumo para Discord: {e}")
    except Exception as e:
        print(f"❌ Erro desconhecido ao enviar notificação Resumo para Discord: {e}")


# O Cloud Run executa este código.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

import os
import discord
import feedparser
import json
import re
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
RSS_URL = os.getenv("RSS_URL")
CONFIG_FILE = "config.json"
GUID_FILE = "sent_guids.json"

# Configuração dos intents do Discord
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
scheduler = AsyncIOScheduler()

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot online!", 200

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Load config and sent_guids
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

if os.path.exists(GUID_FILE):
    with open(GUID_FILE, "r") as f:
        sent_guids = set(json.load(f))
else:
    sent_guids = set()

def save_guids():
    with open(GUID_FILE, "w") as f:
        json.dump(list(sent_guids), f)

config = load_config()

# Função para formatar parágrafos corretamente
def format_paragraphs(text):
    paragraphs = re.split(r'\n{2,}', text.strip())
    return '\n\n'.join(' '.join(p.splitlines()) for p in paragraphs)

def limpar_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([.,;!?])', r'\1', text)
    return text

def dividir_em_blocos(texto):
    leitura = evangelho = reflexao = ""
    if "Proclamação do Evangelho" in texto:
        partes = texto.split("Proclamação do Evangelho de Jesus Cristo segundo")
        leitura = partes[0].strip()
        resto = "Proclamação do Evangelho de Jesus Cristo segundo" + partes[1]
        if "Prefiro gloriar-me das minhas fraquezas" in resto:
            partes_ev = resto.split("Prefiro gloriar-me das minhas fraquezas")
            evangelho = partes_ev[0].strip()
            reflexao = "Prefiro gloriar-me das minhas fraquezas" + partes_ev[1]
        else:
            evangelho = resto.strip()
            reflexao = ""
    else:
        leitura = texto
        evangelho = ""
        reflexao = ""
    return leitura, evangelho, reflexao

def dividir_em_blocos_flexivel(texto):
    # Regex para encontrar títulos de blocos
    padroes = [
        ("leitura", r"(leitura[^:]*:?)", "📖"),
        ("evangelho", r"(proclamação do evangelho[^:]*:?)", "✝️"),
        ("reflexao", r"(reflex[aã]o[^:]*:?)", "🕊️")
    ]
    texto_lower = texto.lower()
    indices = {}
    for nome, padrao, _ in padroes:
        match = re.search(padrao, texto_lower)
        if match:
            indices[nome] = match.start()
    # Ordenar blocos encontrados
    blocos = {}
    nomes_encontrados = sorted(indices.items(), key=lambda x: x[1])
    for i, (nome, idx) in enumerate(nomes_encontrados):
        start = idx
        end = nomes_encontrados[i+1][1] if i+1 < len(nomes_encontrados) else len(texto)
        blocos[nome] = texto[start:end].strip()
    # Garantir que todos existam
    leitura = blocos.get("leitura", "")
    evangelho = blocos.get("evangelho", "")
    reflexao = blocos.get("reflexao", "")
    return leitura, evangelho, reflexao

def formatar_bloco(titulo, texto, emoji):
    if not texto:
        return ""
    return f"{emoji} {titulo}:\n{texto.strip()}\n"

def dividir_bloco_em_mensagens(titulo, texto, emoji, limite=2000):
    if not texto:
        return []
    header = f"{emoji} {titulo}:\n"
    blocos = []
    paragrafos = texto.split('\n')
    bloco_atual = header
    header_usado = False
    for p in paragrafos:
        p = p.strip()
        if not p:
            continue
        # Se o parágrafo for maior que o limite, quebrar o parágrafo
        while len(p) > (limite if header_usado else limite - len(header)):
            parte = p[:(limite if header_usado else limite - len(header))]
            if not header_usado:
                bloco_atual += parte
                blocos.append(bloco_atual.strip())
                bloco_atual = ''
                header_usado = True
            else:
                blocos.append(parte)
            p = p[(limite if header_usado else limite - len(header)):]
        # Se adicionar o parágrafo excede o limite, salva o bloco e começa outro
        if len(bloco_atual) + len(p) + 1 > limite:
            blocos.append(bloco_atual.strip())
            bloco_atual = ''
            header_usado = True
        if bloco_atual:
            bloco_atual += '\n' + p
        else:
            bloco_atual = p
    if bloco_atual.strip():
        blocos.append(bloco_atual.strip())
    return blocos

# Build the Discord embed message
def build_embed(title, date, sec):
    embed = discord.Embed(
        title=f"📖 Palavra do Dia – {title}",
        description=f"🗓️ {date}",
        color=0x2E86C1
    )
    if sec["leitura"]:
        embed.add_field(name="📖 Leitura", value=sec["leitura"][:1024], inline=False)
    if sec["evangelho"]:
        embed.add_field(name="✝️ Evangelho", value=sec["evangelho"][:1024], inline=False)
    if sec["reflexao"]:
        embed.add_field(name="🕊️ Reflexão", value=sec["reflexao"][:1024], inline=False)
    return embed

def dividir_mensagem(texto, header=None, limite=1500):
    # Divide o texto em parágrafos
    paragrafos = texto.split('\n\n')
    blocos = []
    bloco_atual = ''
    for i, p in enumerate(paragrafos):
        p = p.strip()
        if not p:
            continue
        # Se for o primeiro bloco e tiver header
        if not blocos and header:
            bloco_atual = header
        # Se adicionar o parágrafo excede o limite, salva o bloco e começa outro
        if len(bloco_atual) + len(p) + 2 > limite:
            if bloco_atual.strip():
                blocos.append(bloco_atual.strip())
            bloco_atual = ''
            # Se for novo bloco e header já foi, não repete header
        if bloco_atual:
            bloco_atual += '\n\n' + p
        else:
            bloco_atual = p
    if bloco_atual.strip():
        blocos.append(bloco_atual.strip())
    return blocos

# Função para formatar todas as mensagens a serem enviadas
def formatar_mensagens(title_str, date_str, leitura, evangelho, reflexao):
    mensagens = []
    mensagens.append(f"📖 Palavra do Dia – {title_str}\n🗓️ {date_str}")
    mensagens.extend(dividir_bloco_em_mensagens("Leitura", leitura, "📖"))
    mensagens.extend(dividir_bloco_em_mensagens("Evangelho", evangelho, "✝️"))
    mensagens.extend(dividir_bloco_em_mensagens("Reflexão", reflexao, "🕊️"))
    return mensagens

# Função principal que busca e envia a mensagem
async def fetch_and_send(force_send=False):
    try:
        feed = feedparser.parse(RSS_URL)
        entry = feed.entries[0]
        if not force_send and entry.id in sent_guids:
            print("[INFO] Já enviado:", entry.title)
            return

        descricao_html = entry.description
        texto_limpo = limpar_html(descricao_html)
        leitura, evangelho, reflexao = dividir_em_blocos_flexivel(texto_limpo)
        date_str = entry.published
        title_str = entry.title
        mensagens = formatar_mensagens(title_str, date_str, leitura, evangelho, reflexao)

        for guild_id, channel_id in config.items():
            channel = client.get_channel(int(channel_id))
            if channel:
                print(f"[DEBUG] Enviando para canal: {channel.name} ({guild_id})")
                for idx, msg in enumerate(mensagens):
                    print(f"[DEBUG] Mensagem {idx+1}:\n{msg}\n{'-'*40}")
                    await channel.send(msg)
                print(f"[SUCESSO] Enviado para {channel.name} ({guild_id})")
            else:
                print(f"[ERRO] Canal não encontrado para guild {guild_id}")

        if not force_send:
            sent_guids.add(entry.id)
            save_guids()

    except Exception as e:
        print("[ERRO]", str(e))

# Evento: quando o bot está pronto
@client.event
async def on_ready():
    print(f"[INFO] Bot conectado como {client.user}")
    await fetch_and_send()
    scheduler.add_job(fetch_and_send, CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"))
    scheduler.start()
    print("[INFO] Agendamento iniciado.")

# Evento: quando o bot recebe mensagens
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.lower().startswith("!definir"):
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        config[guild_id] = channel_id
        save_config(config)
        await message.channel.send("✅ Este canal foi definido para receber a Palavra do Dia diariamente!")

    elif message.content.lower().startswith("!testar"):
        print("[DEBUG] Comando !testar recebido de:", message.author)
        await fetch_and_send(force_send=True)

# Manter o bot vivo
keep_alive()

# Executa o bot
client.run(TOKEN)

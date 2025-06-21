import os
import discord
import feedparser
import json
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
RSS_URL = os.getenv("RSS_URL")
CONFIG_FILE = "config.json"
GUID_FILE = "sent_guids.json"

# Configuração dos intents do Discord
intents = discord.Intents.default()
intents.message_content = True  # precisa disso para on_message funcionar
client = discord.Client(intents=intents)
scheduler = AsyncIOScheduler()

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

# Parse the RSS content
def parse_sections(html):
    soup = BeautifulSoup(html, "html.parser")
    paras = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
    
    sec = {"leitura": "", "evangelho": "", "reflexao": ""}
    for text in paras:
        lower = text.lower()
        if "leitura" in lower:
            sec["leitura"] += text + "\n\n"
        elif "evangelho" in lower:
            sec["evangelho"] += text + "\n\n"
        else:
            sec["reflexao"] += text + "\n\n"
    return sec

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

# Função principal que busca e envia a mensagem
async def fetch_and_send():
    try:
        feed = feedparser.parse(RSS_URL)
        entry = feed.entries[0]
        if entry.id in sent_guids:
            print("[INFO] Já enviado:", entry.title)
            return

        sections = parse_sections(entry.description)
        embed = build_embed(entry.title, entry.published, sections)

        for guild_id, channel_id in config.items():
            channel = client.get_channel(int(channel_id))
            if channel:
                await channel.send(embed=embed)
                print(f"[SUCESSO] Enviado para {channel.name} ({guild_id})")
            else:
                print(f"[ERRO] Canal não encontrado para guild {guild_id}")

        sent_guids.add(entry.id)
        save_guids()

    except Exception as e:
        print("[ERRO]", str(e))

# Evento: quando o bot está pronto
@client.event
async def on_ready():
    print(f"[INFO] Bot conectado como {client.user}")
    
    # Envia imediatamente ao iniciar
    await fetch_and_send()

    # Agenda envio diário às 08:00 (hora de Brasília)
    scheduler.add_job(fetch_and_send, CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"))
    scheduler.start()

    print("[INFO] Agendamento iniciado.")

# Evento: quando o bot recebe mensagens
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Comando para definir canal
    if message.content.lower().startswith("!definir"):
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        config[guild_id] = channel_id
        save_config(config)
        await message.channel.send("✅ Este canal foi definido para receber a Palavra do Dia diariamente!")

    # Comando para testar envio imediato
    elif message.content.lower().startswith("!testar"):
        await fetch_and_send()
        await message.channel.send("✅ Palavra do Dia enviada manualmente.")

# Função para manter o bot ativo
keep_alive()

# Executa o bot
client.run(TOKEN)
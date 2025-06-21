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
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
RSS_URL = os.getenv("RSS_URL")

# GUID log
GUID_FILE = "sent_guids.json"
if os.path.exists(GUID_FILE):
    with open(GUID_FILE, "r") as f:
        sent_guids = set(json.load(f))
else:
    sent_guids = set()

def save_guids():
    with open(GUID_FILE, "w") as f:
        json.dump(list(sent_guids), f)

# Parse content into sections
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

# Create the embed message
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

# Discord setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)
scheduler = AsyncIOScheduler()

TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

config = load_config()


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

@client.event
async def on_ready():
    print(f"[INFO] Bot conectado como {client.user}")

    # Envia imediatamente ao iniciar
    await fetch_and_send()

    # Continua com agendamento diário às 08:00
    scheduler.add_job(fetch_and_send, CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"))
    scheduler.start()

    print("[INFO] Agendamento iniciado.")


client.run(TOKEN)
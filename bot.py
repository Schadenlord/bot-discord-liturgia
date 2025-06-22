import os
import discord
import requests
import json
import re
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "config.json"

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

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

config = load_config()

def limpar_html(texto):
    soup = BeautifulSoup(texto, 'html.parser')
    text = soup.get_text(separator=' ')
    text = re.sub(r'\\s+', ' ', text).strip()
    return text

def fetch_liturgia_api_nova():
    hoje = date.today().strftime("%Y-%m-%d")
    url = f"https://api-liturgia-diaria.vercel.app/?date={hoje}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Erro ao buscar dados da API")

    dados = response.json()
    dia = dados["today"]
    titulo = limpar_html(dia["entry_title"])
    leitura = f"{dia['readings']['first_reading']['title']}\\n{dia['readings']['first_reading']['head']}\\n{dia['readings']['first_reading']['text']}\\n{dia['readings']['first_reading']['footer']}"
    evangelho = f"{dia['readings']['gospel']['title']}\\n{dia['readings']['gospel']['head_title']}\\n{dia['readings']['gospel']['text']}\\n{dia['readings']['gospel']['footer']}"
    salmo = f"{dia['readings']['psalm']['title']}\\nR: {dia['readings']['psalm']['response']}\\n" + "\\n".join(dia['readings']['psalm']['content_psalm'])
    return titulo, hoje, leitura, evangelho, salmo

def dividir_bloco_em_mensagens(titulo, texto, emoji, limite=2000):
    if not texto:
        return []
    header = f"{emoji} {titulo}:\n"
    blocos = []
    paragrafos = texto.split('\\n')
    bloco_atual = header
    header_usado = False
    for p in paragrafos:
        p = p.strip()
        if not p:
            continue
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
        if len(bloco_atual) + len(p) + 1 > limite:
            blocos.append(bloco_atual.strip())
            bloco_atual = ''
            header_usado = True
        if bloco_atual:
            bloco_atual += '\\n' + p
        else:
            bloco_atual = p
    if bloco_atual.strip():
        blocos.append(bloco_atual.strip())
    return blocos

def formatar_mensagens(title_str, date_str, leitura, evangelho, salmo):
    mensagens = []
    mensagens.append(f"📖 Palavra do Dia – {title_str}\\n🗓️ {date_str}")
    mensagens.extend(dividir_bloco_em_mensagens("Leitura", leitura, "📖"))
    mensagens.extend(dividir_bloco_em_mensagens("Salmo", salmo, "🎶"))
    mensagens.extend(dividir_bloco_em_mensagens("Evangelho", evangelho, "✝️"))
    return mensagens

async def fetch_and_send(force_send=False):
    try:
        hoje = date.today().strftime("%Y-%m-%d")
        url = f"https://api-liturgia-diaria.vercel.app/?date={hoje}"
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception("Erro ao buscar dados da API")

        dados = response.json()
        dia = dados["today"]

        entry_title = limpar_html(dia.get("entry_title", ""))
        color_lit = dia.get("color", "branco").lower()
        date_str = dia.get("date", hoje)

        leitura = (
            f"{dia['readings']['first_reading']['head']}\n\n"
            f"{dia['readings']['first_reading']['text']}\n\n"
            f"{dia['readings']['first_reading']['footer']}"
        ).replace("\\n", "\n")

        salmo = (
            f"{dia['readings']['psalm']['title']}\n\n"
            f"{dia['readings']['psalm']['response']}\n\n" +
            "\n".join(dia['readings']['psalm']['content_psalm'])
        ).replace("\\n", "\n")

        evangelho = (
            f"{dia['readings']['gospel']['head_title']}\n\n"
            f"{dia['readings']['gospel']['text']}\n\n"
            f"{dia['readings']['gospel']['footer']}"
        ).replace("\\n", "\n")

        cores = {
            "verde": 0x228B22,
            "vermelho": 0xB22222,
            "roxo": 0x800080,
            "branco": 0xF8F8FF,
            "rosa": 0xFFC0CB,
            "preto": 0x111111
        }
        cor_embed = cores.get(color_lit, 0xAAAAAA)

        embed = discord.Embed(
            title="📜 Proclamação da Liturgia",
            description=(
                f"{entry_title}\n"
                f"📅 {date_str}\n"
                f"🕯️ Cor litúrgica: **{color_lit.capitalize()}**"
            ),
            color=cor_embed
        )


        def cortar(texto):
            return texto if len(texto) < 1024 else texto[:1020] + "..."

        embed.add_field(name="📖 Letanía da Palavra", value=cortar(leitura), inline=False)
        embed.add_field(name="🎶 Salmodia Real", value=cortar(salmo), inline=False)
        embed.add_field(name="✝️ Evangelho Sagrado", value=cortar(evangelho), inline=False)

        embed.set_footer(text="Scriptor Sacrum · O Escriba da Aurora")
        embed.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/b/ba/Emblem_of_the_Holy_See_%28no_background%29.svg/1510px-Emblem_of_the_Holy_See_%28no_background%29.svg.png")

        # Envio para todos os canais
        for guild_id, channel_id in config.items():
            channel = client.get_channel(int(channel_id))
            if channel:
                await channel.send(embed=embed)
                print(f"[SUCESSO] Liturgia enviada para {channel.name}")

                # Se houver meditação no campo "extra"
                extra = dia.get("extra", [])
                if extra:
                    meditacao = "\n".join([limpar_html(l) for l in extra if l.strip()])
                    if meditacao:
                        embed_meditacao = discord.Embed(
                            title="🕊️ Meditação do Dia",
                            description=meditacao,
                            color=0x7FDBFF
                        )
                        embed_meditacao.set_footer(text="Scriptor Sacrum · O Escriba da Aurora")
                        embed_meditacao.set_thumbnail(url="https://upload.wikimedia.org/wikipedia/commons/thumb/b/ba/Emblem_of_the_Holy_See_%28no_background%29.svg/1510px-Emblem_of_the_Holy_See_%28no_background%29.svg.png")
                        await channel.send(embed=embed_meditacao)
                        print(f"[SUCESSO] Meditação enviada para {channel.name}")
            else:
                print(f"[ERRO] Canal não encontrado para guild {guild_id}")

    except Exception as e:
        print("[ERRO]", str(e))


@client.event
async def on_ready():
    print(f"[INFO] Bot conectado como {client.user}")
    await fetch_and_send()
    scheduler.add_job(fetch_and_send, CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"))
    scheduler.start()
    print("[INFO] Agendamento iniciado.")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.lower().startswith("!definir"):
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        config[guild_id] = channel_id
        save_config(config)
        await message.channel.send("✅ Canal definido para receber a Liturgia Diária!")
    elif message.content.lower().startswith("!testar"):
        await fetch_and_send(force_send=True)

keep_alive()
client.run(TOKEN)

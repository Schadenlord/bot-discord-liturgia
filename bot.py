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

                # Terço do dia
                misterios_do_terco = {
                    "segunda-feira": {
                        "tipo": "Gozosos",
                        "mistérios": [
                            {"título": "A Anunciação do Anjo a Maria", "descrição": "O anjo Gabriel anuncia a Maria que ela será a Mãe do Salvador. (Lc 1,26-38)"},
                            {"título": "A Visitação de Maria a Isabel", "descrição": "Maria visita sua prima Isabel, que também espera um filho (João Batista). (Lc 1,39-56)"},
                            {"título": "O Nascimento de Jesus em Belém", "descrição": "Jesus nasce em um estábulo, em humildade e pobreza. (Lc 2,1-20)"},
                            {"título": "A Apresentação de Jesus no Templo", "descrição": "Maria e José apresentam Jesus ao Senhor no templo. (Lc 2,22-38)"},
                            {"título": "O Encontro do Menino Jesus no Templo", "descrição": "Jesus, com 12 anos, é encontrado entre os doutores da Lei. (Lc 2,41-50)"}
                        ]
                    },
                    "terça-feira": {
                        "tipo": "Dolorosos",
                        "mistérios": [
                            {"título": "A Agonia de Jesus no Horto", "descrição": "Jesus sua sangue e reza ao Pai antes de ser preso. (Mt 26,36-46)"},
                            {"título": "A Flagelação de Jesus", "descrição": "Jesus é cruelmente açoitado. (Jo 19,1)"},
                            {"título": "A Coroação de Espinhos", "descrição": "Soldados zombam de Jesus, coroando-O com espinhos. (Mt 27,27-31)"},
                            {"título": "Jesus Carrega a Cruz até o Calvário", "descrição": "Jesus carrega Sua cruz até o lugar da crucificação. (Jo 19,17)"},
                            {"título": "A Crucificação e Morte de Jesus", "descrição": "Jesus morre na cruz para a salvação da humanidade. (Lc 23,33-46)"}
                        ]
                    },
                    "quarta-feira": {
                        "tipo": "Gloriosos",
                        "mistérios": [
                            {"título": "A Ressurreição de Jesus", "descrição": "Jesus ressuscita dos mortos ao terceiro dia. (Mt 28,1-10)"},
                            {"título": "A Ascensão de Jesus ao Céu", "descrição": "Jesus sobe aos céus à vista dos apóstolos. (At 1,6-11)"},
                            {"título": "A Vinda do Espírito Santo", "descrição": "O Espírito Santo desce sobre os apóstolos. (At 2,1-4)"},
                            {"título": "A Assunção de Maria", "descrição": "Maria é elevada em corpo e alma ao Céu. (Ap 12)"},
                            {"título": "A Coroação de Maria", "descrição": "Maria é coroada por Deus como Rainha do Céu e da Terra. (Ap 12,1)"}
                        ]
                    },
                    "quinta-feira": {
                        "tipo": "Luminosos",
                        "mistérios": [
                            {"título": "O Batismo de Jesus no Jordão", "descrição": "Jesus é batizado por João Batista e o Espírito Santo desce sobre Ele. (Mt 3,13-17)"},
                            {"título": "As Bodas de Caná", "descrição": "Jesus realiza seu primeiro milagre, transformando água em vinho. (Jo 2,1-12)"},
                            {"título": "O Anúncio do Reino de Deus", "descrição": "Jesus prega, cura e chama todos à conversão. (Mc 1,14-15)"},
                            {"título": "A Transfiguração de Jesus", "descrição": "Jesus aparece em glória com Moisés e Elias no monte Tabor. (Lc 9,28-36)"},
                            {"título": "A Instituição da Eucaristia", "descrição": "Jesus oferece seu Corpo e Sangue sob o pão e o vinho na Última Ceia. (Lc 22,14-20)"}
                        ]
                    },
                    "sexta-feira": {
                        "tipo": "Dolorosos",
                        "mistérios": [
                            {"título": "A Agonia de Jesus no Horto", "descrição": "Jesus sua sangue e reza ao Pai antes de ser preso. (Mt 26,36-46)"},
                            {"título": "A Flagelação de Jesus", "descrição": "Jesus é cruelmente açoitado. (Jo 19,1)"},
                            {"título": "A Coroação de Espinhos", "descrição": "Soldados zombam de Jesus, coroando-O com espinhos. (Mt 27,27-31)"},
                            {"título": "Jesus Carrega a Cruz até o Calvário", "descrição": "Jesus carrega Sua cruz até o lugar da crucificação. (Jo 19,17)"},
                            {"título": "A Crucificação e Morte de Jesus", "descrição": "Jesus morre na cruz para a salvação da humanidade. (Lc 23,33-46)"}
                        ]
                    },
                    "sábado": {
                        "tipo": "Gozosos",
                        "mistérios": [
                            {"título": "A Anunciação do Anjo a Maria", "descrição": "O anjo Gabriel anuncia a Maria que ela será a Mãe do Salvador. (Lc 1,26-38)"},
                            {"título": "A Visitação de Maria a Isabel", "descrição": "Maria visita sua prima Isabel, que também espera um filho (João Batista). (Lc 1,39-56)"},
                            {"título": "O Nascimento de Jesus em Belém", "descrição": "Jesus nasce em um estábulo, em humildade e pobreza. (Lc 2,1-20)"},
                            {"título": "A Apresentação de Jesus no Templo", "descrição": "Maria e José apresentam Jesus ao Senhor no templo. (Lc 2,22-38)"},
                            {"título": "O Encontro do Menino Jesus no Templo", "descrição": "Jesus, com 12 anos, é encontrado entre os doutores da Lei. (Lc 2,41-50)"}
                        ]
                    },
                    "domingo": {
                        "tipo": "Gloriosos",
                        "observação": "Pode-se rezar os Luminosos no Tempo Comum, se preferir.",
                        "mistérios": [
                            {"título": "A Ressurreição de Jesus", "descrição": "Jesus ressuscita dos mortos ao terceiro dia. (Mt 28,1-10)"},
                            {"título": "A Ascensão de Jesus ao Céu", "descrição": "Jesus sobe aos céus à vista dos apóstolos. (At 1,6-11)"},
                            {"título": "A Vinda do Espírito Santo", "descrição": "O Espírito Santo desce sobre os apóstolos. (At 2,1-4)"},
                            {"título": "A Assunção de Maria", "descrição": "Maria é elevada em corpo e alma ao Céu. (Ap 12)"},
                            {"título": "A Coroação de Maria", "descrição": "Maria é coroada por Deus como Rainha do Céu e da Terra. (Ap 12,1)"}
                        ]
                    }
                }
                dias_pt = [
                    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"
                ]
                dia_semana = dias_pt[date.today().weekday()]
                terco = misterios_do_terco[dia_semana]
                descricao_terco = f"**Mistérios {terco['tipo']}**\n\n"
                for idx, misterio in enumerate(terco["mistérios"], 1):
                    descricao_terco += f"{idx}. **{misterio['título']}**\n{misterio['descrição']}\n\n"
                if 'observação' in terco:
                    descricao_terco += f"\n_Observação: {terco['observação']}_"
                embed_terco = discord.Embed(
                    title=f"📿 Terço do Dia – {dia_semana.capitalize()}",
                    description=descricao_terco,
                    color=0xFFD700
                )
                embed_terco.set_footer(text="Scriptor Sacrum · O Escriba da Aurora")
                embed_terco.set_thumbnail(url="https://yata-apix-9da23243-671c-42a8-9014-41a94dafae05.s3-object.locaweb.com.br/ae792e6635b3427f9ab1f5ed4774e121.png")
                await channel.send(embed=embed_terco)
                print(f"[SUCESSO] Terço enviado para {channel.name}")
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

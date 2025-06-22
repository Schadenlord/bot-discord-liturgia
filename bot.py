import os
import discord
import requests
import json
import re
import asyncio
from datetime import date, datetime, time, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "config.json"
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID", 1386432203486920845))  # Canal de voz para o áudio do terço
GUILD_ID = int(os.getenv("GUILD_ID", 1307006114612908083))

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

async def enviar_liturgia_e_terco_texto(force_send=False):
    try:
        print("[DEBUG] Iniciando envio da liturgia e terço em texto...")
        hoje = date.today().strftime("%Y-%m-%d")
        url = f"https://api-liturgia-diaria.vercel.app/?date={hoje}"
        print(f"[DEBUG] Buscando dados da API: {url}")
        response = requests.get(url)
        if response.status_code != 200:
            print(f"[ERRO] Status da API: {response.status_code}")
            raise Exception("Erro ao buscar dados da API")

        dados = response.json()
        dia = dados["today"]

        entry_title = limpar_html(dia.get("entry_title", ""))
        color_lit = dia.get("color", "branco").lower()
        date_str = dia.get("date", hoje)

        print(f"[DEBUG] Dados recebidos: entry_title={entry_title}, color={color_lit}, date={date_str}")

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

        print("[DEBUG] Mensagens formatadas para leitura, salmo e evangelho.")

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

        print(f"[DEBUG] Enviando para {len(config)} canais configurados...")
        # Envio para todos os canais definidos
        for guild_id, channel_id in config.items():
            print(f"[DEBUG] Tentando enviar para guild_id={guild_id}, channel_id={channel_id}")
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

                # Terço do dia (texto)
                print(f"[DEBUG] Enviando terço em texto para {channel.name}")
                await enviar_terco_texto(channel)
            else:
                print(f"[ERRO] Canal não encontrado para guild {guild_id}")

    except Exception as e:
        print("[ERRO]", str(e))

async def enviar_terco_texto(channel):
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

    # Adiciona aviso sobre o terço em latim
    guild = client.get_guild(GUILD_ID)
    voice_channel = guild.get_channel(VOICE_CHANNEL_ID) if guild else None
    canal_nome = voice_channel.name if voice_channel else "Canal de voz não encontrado"
    aviso_latim = (
        f"🔔 O terço já foi transmitido hoje em latim neste canal de voz: **{canal_nome}**.\n"
        f"Será transmitido novamente em português às **18h** e em latim às **22h** (horário de São Paulo) no mesmo canal."
    )
    embed_terco.add_field(
        name="ℹ️ Aviso sobre o Terço em Latim",
        value=aviso_latim,
        inline=False
    )

    await channel.send(embed=embed_terco)
    print(f"[SUCESSO] Terço enviado para {channel.name}")

async def tocar_terco_audio(ignorar_espera=False):
    print("[INFO] Preparando para iniciar o Terço em áudio...")
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print("[ERRO] Guild não encontrada. Verifique o GUILD_ID.")
        return

    voice_channel = guild.get_channel(VOICE_CHANNEL_ID)
    if not voice_channel or not isinstance(voice_channel, discord.VoiceChannel):
        print("[ERRO] Canal de voz inválido ou não encontrado.")
        return

    try:
        # Verifica se já está conectado
        if client.voice_clients and any(vc.channel == voice_channel for vc in client.voice_clients):
            voice_client = next(vc for vc in client.voice_clients if vc.channel == voice_channel)
            print(f"[INFO] Já conectado ao canal de voz: {voice_channel.name}")
        else:
            print("[DEBUG] Tentando conectar ao canal de voz...")
            voice_client = await voice_channel.connect()
            print(f"[INFO] Conectado ao canal de voz: {voice_channel.name}")

        # Espera até 18h00 apenas se não for ignorar_espera
        if not ignorar_espera:
            agora = datetime.now(timezone(timedelta(hours=-3)))
            inicio_terco = datetime.combine(agora.date(), time(18, 0), tzinfo=agora.tzinfo)
            segundos_ate_inicio = (inicio_terco - agora).total_seconds()
            if segundos_ate_inicio > 0:
                print(f"[INFO] Aguardando {segundos_ate_inicio:.1f} segundos até 18h")
                await asyncio.sleep(segundos_ate_inicio)

        caminho, tipo = caminho_audio_terco()
        print(f"[DEBUG] Caminho do áudio: {caminho}")
        print(f"[DEBUG] Verificando existência do arquivo de áudio...")
        if not os.path.exists(caminho):
            print(f"[ERRO] Áudio não encontrado: {caminho}")
            await voice_client.disconnect()
            return

        print(f"[INFO] Tocando o Terço ({tipo}) agora...")
        print(f"[DEBUG] Criando FFmpegPCMAudio...")
        try:
            audio_source = discord.FFmpegPCMAudio(executable="./bin/ffmpeg", source=caminho)
        except Exception as e:
            print(f"[ERRO] Erro ao criar FFmpegPCMAudio: {e}")
            await voice_client.disconnect()
            return

        print(f"[DEBUG] Iniciando reprodução do áudio...")
        try:
            voice_client.play(audio_source)
        except Exception as e:
            print(f"[ERRO] Erro ao iniciar reprodução: {e}")
            import traceback
            traceback.print_exc()
            await voice_client.disconnect()
            return

        print(f"[DEBUG] Esperando o áudio terminar...")
        while voice_client.is_playing():
            await asyncio.sleep(1)

        print("[INFO] Terço finalizado. Permanecendo em silêncio por 10 minutos...")
        await asyncio.sleep(600)

        await voice_client.disconnect()
        print("[INFO] Desconectado do canal de voz após silêncio.")
    except Exception as e:
        print(f"[ERRO] Falha ao executar transmissão do terço: {e}")
        import traceback
        traceback.print_exc()
        if 'voice_client' in locals() and voice_client.is_connected():
            await voice_client.disconnect()

def tipo_misterio_hoje():
    dias = {
        0: "gozosos",     # Segunda
        1: "dolorosos",   # Terça
        2: "gloriosos",   # Quarta
        3: "luminosos",   # Quinta
        4: "dolorosos",   # Sexta
        5: "gozosos",     # Sábado
        6: "gloriosos"    # Domingo
    }
    return dias[datetime.now().weekday()]

def caminho_audio_terco():
    tipo = tipo_misterio_hoje()
    return f"audio/{tipo}.mp3", tipo.capitalize()

def caminho_audio_terco_latim():
    tipo = tipo_misterio_hoje()
    return f"audio_latim/{tipo}.mp3", tipo.capitalize()

async def tocar_terco_audio_latim(ignorar_espera=False):
    print("[INFO] Preparando para iniciar o Terço em latim...")
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print("[ERRO] Guild não encontrada. Verifique o GUILD_ID.")
        return

    voice_channel = guild.get_channel(VOICE_CHANNEL_ID)
    if not voice_channel or not isinstance(voice_channel, discord.VoiceChannel):
        print("[ERRO] Canal de voz inválido ou não encontrado.")
        return

    try:
        # Verifica se já está conectado
        if client.voice_clients and any(vc.channel == voice_channel for vc in client.voice_clients):
            voice_client = next(vc for vc in client.voice_clients if vc.channel == voice_channel)
            print(f"[INFO] Já conectado ao canal de voz: {voice_channel.name}")
        else:
            print("[DEBUG] Tentando conectar ao canal de voz...")
            voice_client = await voice_channel.connect()
            print(f"[INFO] Conectado ao canal de voz: {voice_channel.name}")

        # Espera até o horário agendado, se não for ignorar_espera
        if not ignorar_espera:
            agora = datetime.now(timezone(timedelta(hours=-3)))
            # Determina o próximo horário agendado (6h ou 22h)
            hora_atual = agora.hour
            if hora_atual < 6:
                proxima = datetime.combine(agora.date(), time(6, 0), tzinfo=agora.tzinfo)
            elif hora_atual < 22:
                proxima = datetime.combine(agora.date(), time(22, 0), tzinfo=agora.tzinfo)
            else:
                proxima = datetime.combine(agora.date() + timedelta(days=1), time(6, 0), tzinfo=agora.tzinfo)
            segundos_ate_inicio = (proxima - agora).total_seconds()
            if segundos_ate_inicio > 0:
                print(f"[INFO] Aguardando {segundos_ate_inicio:.1f} segundos até o próximo horário agendado")
                await asyncio.sleep(segundos_ate_inicio)

        caminho, tipo = caminho_audio_terco_latim()
        print(f"[DEBUG] Caminho do áudio latim: {caminho}")
        print(f"[DEBUG] Verificando existência do arquivo de áudio...")
        if not os.path.exists(caminho):
            print(f"[ERRO] Áudio não encontrado: {caminho}")
            await voice_client.disconnect()
            return

        print(f"[INFO] Tocando o Terço em latim ({tipo}) agora...")
        print(f"[DEBUG] Criando FFmpegPCMAudio...")
        try:
            audio_source = discord.FFmpegPCMAudio(executable="./bin/ffmpeg", source=caminho)
        except Exception as e:
            print(f"[ERRO] Erro ao criar FFmpegPCMAudio: {e}")
            await voice_client.disconnect()
            return

        print(f"[DEBUG] Iniciando reprodução do áudio...")
        try:
            voice_client.play(audio_source)
        except Exception as e:
            print(f"[ERRO] Erro ao iniciar reprodução: {e}")
            import traceback
            traceback.print_exc()
            await voice_client.disconnect()
            return

        print(f"[DEBUG] Esperando o áudio terminar...")
        while voice_client.is_playing():
            await asyncio.sleep(1)

        print("[INFO] Terço em latim finalizado. Permanecendo em silêncio por 10 minutos...")
        await asyncio.sleep(600)

        await voice_client.disconnect()
        print("[INFO] Desconectado do canal de voz após silêncio.")
    except Exception as e:
        print(f"[ERRO] Falha ao executar transmissão do terço em latim: {e}")
        import traceback
        traceback.print_exc()
        if 'voice_client' in locals() and voice_client.is_connected():
            await voice_client.disconnect()

@client.event
async def on_ready():
    print(f"[INFO] Bot conectado como {client.user}")
    await enviar_liturgia_e_terco_texto()
    # Liturgia e terço em texto às 8h
    scheduler.add_job(enviar_liturgia_e_terco_texto, CronTrigger(hour=8, minute=0, timezone="America/Sao_Paulo"))
    # Terço em áudio: conecta às 17:57, toca às 18:00
    scheduler.add_job(tocar_terco_audio, CronTrigger(hour=17, minute=57, timezone="America/Sao_Paulo"))
    # Terço em latim: às 6h e às 22h
    scheduler.add_job(tocar_terco_audio_latim, CronTrigger(hour=6, minute=0, timezone="America/Sao_Paulo"))
    scheduler.add_job(tocar_terco_audio_latim, CronTrigger(hour=22, minute=0, timezone="America/Sao_Paulo"))
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
        await enviar_liturgia_e_terco_texto(force_send=True)
    elif message.content.lower().startswith("!terco") or message.content.lower().startswith("!terço"):
        await message.channel.send("⏳ Iniciando o terço em áudio no canal de voz configurado...")
        await tocar_terco_audio(ignorar_espera=True)
    elif message.content.lower().startswith("!tertiolatinum"):
        await message.channel.send("⏳ Iniciando o terço em latim no canal de voz configurado...")
        await tocar_terco_audio_latim(ignorar_espera=True)
    elif message.content.lower().startswith("!desconectar"):
        if client.voice_clients:
            for vc in client.voice_clients:
                await vc.disconnect()
            await message.channel.send("🔌 Bot desconectado do canal de voz.")
        else:
            await message.channel.send("❌ O bot não está conectado a nenhum canal de voz.")

keep_alive()
client.run(TOKEN)

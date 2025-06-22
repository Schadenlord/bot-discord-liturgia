import os
import asyncio
import discord
from datetime import datetime, time, timedelta, timezone
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 1307006114612908083))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 1386432203486920845))  # Atualizado para o canal de voz comum

# Mistérios por dia da semana
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

# Discord setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"[INFO] Bot conectado como {client.user}")
    tocar_terco_diario.start()

@tasks.loop(time=time(hour=17, minute=57, tzinfo=timezone(timedelta(hours=-3))))
async def tocar_terco_diario():
    print("[INFO] Preparando para iniciar o Terço...")
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print("[ERRO] Guild não encontrada. Verifique o GUILD_ID.")
        return

    voice_channel = guild.get_channel(CHANNEL_ID)

    if not voice_channel or not isinstance(voice_channel, discord.VoiceChannel):
        print("[ERRO] Canal de voz inválido ou não encontrado.")
        return

    try:
        # Verifica se já está conectado
        if client.voice_clients and any(vc.channel == voice_channel for vc in client.voice_clients):
            voice_client = next(vc for vc in client.voice_clients if vc.channel == voice_channel)
            print(f"[INFO] Já conectado ao canal de voz: {voice_channel.name}")
        else:
            voice_client = await voice_channel.connect()
            print(f"[INFO] Conectado ao canal de voz: {voice_channel.name}")

        # Espera até 18h00
        agora = datetime.now(timezone(timedelta(hours=-3)))
        inicio_terco = datetime.combine(agora.date(), time(18, 0), tzinfo=agora.tzinfo)
        segundos_ate_inicio = (inicio_terco - agora).total_seconds()

        if segundos_ate_inicio > 0:
            print(f"[INFO] Aguardando {segundos_ate_inicio:.1f} segundos até 18h")
            await asyncio.sleep(segundos_ate_inicio)

        # Tocar o terço
        caminho, tipo = caminho_audio_terco()
        if not os.path.exists(caminho):
            print(f"[ERRO] Áudio não encontrado: {caminho}")
            await voice_client.disconnect()
            return

        print(f"[INFO] Tocando o Terço ({tipo}) às 18h em ponto...")
        audio_source = discord.FFmpegPCMAudio(executable="./bin/ffmpeg", source=caminho)
        voice_client.play(audio_source)

        # Espera até o áudio terminar
        while voice_client.is_playing():
            await asyncio.sleep(1)

        # Silêncio por 10 minutos
        print("[INFO] Terço finalizado. Permanecendo em silêncio por 10 minutos...")
        await asyncio.sleep(600)

        await voice_client.disconnect()
        print("[INFO] Desconectado do canal de voz após silêncio.")
    except Exception as e:
        print(f"[ERRO] Falha ao executar transmissão do terço: {e}")
        # Garante que desconecta em caso de erro
        if 'voice_client' in locals() and voice_client.is_connected():
            await voice_client.disconnect()

# Execução
if __name__ == "__main__":
    client.run(TOKEN)
        # Garante que desconecta em caso de erro
        if 'voice_client' in locals() and voice_client.is_connected():
            await voice_client.disconnect()

# Execução
if __name__ == "__main__":
    client.run(TOKEN)

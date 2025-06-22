#!/usr/bin/env bash
set -e

# Instala ffmpeg e opus
apt-get update && apt-get install -y ffmpeg libopus0 libopus-dev

# Inicia o bot
python bot.py

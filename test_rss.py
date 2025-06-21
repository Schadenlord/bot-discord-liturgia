import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

URL = "https://www.vaticannews.va/pt/palavra-do-dia.rss.xml"

def limpar_html(html):
    """Remove tags HTML e converte entidades HTML para texto normal"""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ')
    # Remove múltiplos espaços e espaços antes de pontuação
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([.,;!?])', r'\1', text)
    return text

def dividir_em_blocos(texto):
    """Divide texto em blocos com base em marcadores conhecidos"""
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
    else:
        leitura = texto

    return leitura, evangelho, reflexao

def formatar_bloco(titulo, texto, emoji):
    """Formata um bloco com emoji e título"""
    if not texto:
        return ""
    return f"{emoji} {titulo}:\n{texto.strip()}\n"

def formatar_data(data_str):
    """Converte data do RSS para formato '21 de junho de 2025'"""
    try:
        dt = datetime.strptime(data_str, "%a, %d %b %Y %H:%M:%S %z")
        meses_pt = {
            "January": "janeiro", "February": "fevereiro", "March": "março", "April": "abril",
            "May": "maio", "June": "junho", "July": "julho", "August": "agosto",
            "September": "setembro", "October": "outubro", "November": "novembro", "December": "dezembro"
        }
        mes_extenso = dt.strftime("%B")
        return dt.strftime(f"%d de {meses_pt[mes_extenso]} de %Y")
    except Exception:
        return data_str

def main():
    logging.info(f"Buscando RSS: {URL}")
    resp = requests.get(URL)
    soup = BeautifulSoup(resp.content, features="xml")
    item = soup.find("item")
    
    titulo = item.find("title").text
    pubdate = item.find("pubDate").text
    descricao_html = item.find("description").text

    texto_limpo = limpar_html(descricao_html)
    leitura, evangelho, reflexao = dividir_em_blocos(texto_limpo)

    data_formatada = formatar_data(pubdate)

    print(f"\n📖 Palavra do Dia – {data_formatada}")
    print(f"🗓️ {pubdate}\n")

    print(formatar_bloco("Leitura", leitura, "📖"))
    print(formatar_bloco("Evangelho", evangelho, "✝️"))
    print(formatar_bloco("Reflexão", reflexao, "🕊️"))

if __name__ == "__main__":
    main()

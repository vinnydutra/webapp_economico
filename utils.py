import json
import os
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = "https://iaealuasigceyzpbarvf.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZWFsdWFzaWdjZXl6cGJhcnZmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgzNzQ1NTEsImV4cCI6MjA2Mzk1MDU1MX0.ohrzecHP0MuQq-T9lyUdu2Jo6NAH5OWsgk8oKjXEQV8"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Todas as funções agora dependem de uma variável 'usuario' que precisa ser capturada no início da execução via obter_usuario()

# Função para capturar o nome do usuário
def obter_usuario():
    if "usuario" not in st.session_state:
        usuario = st.sidebar.text_input("Digite seu nome de usuário:", key="usuario_input")
        if usuario:
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.stop()
    return st.session_state.usuario


# Função para gerar o caminho do arquivo da carteira com base no usuário
def caminho_arquivo_carteira(usuario):
    if isinstance(usuario, str) and not isinstance(usuario, list):
        usuario_limpo = usuario.lower().replace('carteira_', '').replace(' ', '_')
        return f"carteira_{usuario_limpo}.json"
    else:
        raise ValueError("O nome de usuário deve ser uma string e não uma lista.")


def carregar_carteira(usuario):
    caminho = caminho_arquivo_carteira(usuario)
    if os.path.exists(caminho):
        with open(caminho, "r") as file:
            dados = json.load(file)
            return dados
    else:
        return {"favoritos_analise": [], "posicao_atual": []}


# Função para salvar a carteira do usuário
def salvar_carteira(dados, usuario):
    caminho = caminho_arquivo_carteira(usuario)
    with open(caminho, "w") as file:
        json.dump(dados, file, indent=4)


def carregar_carteira_supabase(usuario):
    response = supabase.table("carteira").select("*").eq("usuario", usuario).execute()
    if response.data:
        return response.data
    else:
        return []


def inserir_ativo_carteira(usuario, ticker, quantidade, custo, data_compra):
    dados = {
        "usuario": usuario,
        "ticker": ticker,
        "quantidade": quantidade,
        "custo": custo,
        "data_compra": data_compra
    }
    supabase.table("carteira").insert(dados).execute()


def deletar_ativo_carteira(usuario, ticker):
    supabase.table("carteira").delete().eq("usuario", usuario).eq("ticker", ticker).execute()


def atualizar_ativo_carteira(usuario, ticker, quantidade, custo, data_compra):
    dados = {
        "quantidade": quantidade,
        "custo": custo,
        "data_compra": data_compra
    }
    supabase.table("carteira").update(dados).eq("usuario", usuario).eq("ticker", ticker).execute()


# Função utilitária para formatar grandes números com ou sem moeda
def formatar_valor(valor, moeda=True):
    if valor is None:
        return "Não disponível"
    if moeda:
        if valor >= 1_000_000_000_000:
            return f"R$ {valor/1_000_000_000_000:.2f} Trilhões"
        elif valor >= 1_000_000_000:
            return f"R$ {valor/1_000_000_000:.2f} Bilhões"
        elif valor >= 1_000_000:
            return f"R$ {valor/1_000_000:.2f} Milhões"
        else:
            return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    else:
        if valor >= 1_000_000_000_000:
            return f"{valor/1_000_000_000_000:.2f} Trilhões"
        elif valor >= 1_000_000_000:
            return f"{valor/1_000_000_000:.2f} Bilhões"
        elif valor >= 1_000_000:
            return f"{valor/1_000_000:.2f} Milhões"
        else:
            return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
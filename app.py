import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import os

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Meril Life | Cloud", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
# O link da planilha será configurado nos Secrets do Streamlit Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

# Função para carregar dados de qualquer aba
def carregar_dados(aba):
    return conn.read(worksheet=aba, ttl="0s") # ttl=0 garante que pegue o dado mais recente

# --- CSS E ESTADO (Mantidos da Fase 2) ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'pagina_ativa' not in st.session_state: st.session_state['pagina_ativa'] = "Dashboard"

# --- INTERFACE DE LOGIN (Simplificada para o exemplo) ---
if not st.session_state['logged_in']:
    st.title("Acesso Meril Cloud")
    senha = st.text_input("Senha de Acesso", type="password")
    if st.button("Entrar"):
        if senha == "meril2025": # Altere para sua senha
            st.session_state['logged_in'] = True
            st.rerun()
        else:
            st.error("Senha incorreta")
    st.stop()

# --- NAVEGAÇÃO ---
menu = ["Dashboard", "Novo Registro", "Consulta"]
sel = st.sidebar.radio("Menu", menu)

# ==============================================================================
# ABA: NOVO REGISTRO (SALVANDO NO GOOGLE)
# ==============================================================================
if sel == "Novo Registro":
    st.title("Novo Procedimento (Cloud)")
    
    # Carrega listas auxiliares das abas da planilha para os selects
    # (Você deve criar abas chamadas 'hospitais', 'especialistas', etc na planilha)
    try:
        lista_hospitais = carregar_dados("hospitais")['nome'].tolist()
        lista_especialistas = carregar_dados("especialistas")['nome'].tolist()
    except:
        lista_hospitais = ["Hospital A", "Hospital B"] # Fallback caso as abas não existam
        lista_especialistas = ["Especialista 1"]

    with st.form("form_registro"):
        col1, col2 = st.columns(2)
        f_data = col1.date_input("Data", date.today())
        f_paciente = col2.text_input("Paciente (Iniciais)")
        f_hosp = col1.selectbox("Hospital", lista_hospitais)
        f_spec = col2.selectbox("Especialista", lista_especialistas)
        f_obs = st.text_area("Comentários")
        
        btn_salvar = st.form_submit_button("Enviar para Planilha")
        
        if btn_salvar:
            # Cria um DataFrame com a nova linha
            novo_registro = pd.DataFrame([{
                "Data": f_data.strftime('%Y-%m-%d'),
                "Paciente": f_paciente,
                "Hospital": f_hosp,
                "Especialista": f_spec,
                "Comentarios": f_obs
            }])
            
            # Carrega o que já existe
            df_existente = carregar_dados("procedimentos")
            
            # Junta o novo com o antigo
            df_final = pd.concat([df_existente, novo_registro], ignore_index=True)
            
            # Atualiza a planilha inteira
            conn.update(worksheet="procedimentos", data=df_final)
            st.success("Dados salvos com sucesso no Google Sheets!")

# ==============================================================================
# ABA: CONSULTA
# ==============================================================================
elif sel == "Consulta":
    st.title("Base de Dados em Tempo Real")
    df = carregar_dados("procedimentos")
    st.dataframe(df, use_container_width=True)
    
    if st.button("Atualizar Dados"):
        st.rerun()

# ==============================================================================
# ABA: DASHBOARD
# ==============================================================================
elif sel == "Dashboard":
    st.title("Indicadores Meril")
    df = carregar_dados("procedimentos")
    if not df.empty:
        st.metric("Total de Cirurgias", len(df))
        st.bar_chart(df['Hospital'].value_counts())
    else:
        st.info("Nenhum dado encontrado na planilha.")

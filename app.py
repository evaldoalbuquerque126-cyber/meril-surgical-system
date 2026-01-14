import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, date
import time
from fpdf import FPDF

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meril Life | Surgical Intelligence",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTES E ARQUIVOS ---
ARQUIVO_DB = 'myval_dados.db'
ARQUIVO_CSV = 'dados.csv' 
LOGO_URL_BACKUP = "https://cdn-icons-png.flaticon.com/512/3063/3063176.png"
LOGO_FILE = "logo.png" # Salve o logo da Meril com este nome na pasta

# --- ESTILIZAÇÃO CSS (PREMIUM) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Roboto', sans-serif; color: #333; }
    .stApp { background-color: #F4F6F9; }
    
    /* Login Screen */
    .login-box { 
        background: white; padding: 40px; border-radius: 10px; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; 
    }
    
    /* Sidebar e Headers */
    section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E0E0E0; }
    h1, h2, h3 { color: #003B73; font-weight: 700; }
    
    /* Botões */
    .stButton button {
        background-color: #003B73; color: white; border-radius: 4px; border: none; transition: 0.3s;
    }
    .stButton button:hover { background-color: #00AEEF; color: white; }
    
    /* KPIs */
    div[data-testid="metric-container"] {
        background-color: #FFFFFF; border-left: 5px solid #00AEEF; 
        padding: 15px; border-radius: 6px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# --- GESTÃO DE SESSÃO E LOGIN ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = None
if 'role' not in st.session_state: st.session_state['role'] = None
if 'registro_atual' not in st.session_state: st.session_state['registro_atual'] = None 
if 'modo_visualizacao' not in st.session_state: st.session_state['modo_visualizacao'] = False 
if 'pagina_ativa' not in st.session_state: st.session_state['pagina_ativa'] = "Dashboard"

# Usuários Hardcoded (Em produção real, isso ficaria no Banco de Dados)
USERS = {
    "admin": {"pass": "admin123", "role": "admin", "name": "Administrador"},
    "meril": {"pass": "meril2025", "role": "user", "name": "Gerente Regional"},
}

# --- FUNÇÕES DE BANCO DE DADOS ---
def get_conn(): return sqlite3.connect(ARQUIVO_DB)

def run_action(query, params=()):
    conn = get_conn()
    try:
        conn.execute(query, params)
        conn.commit()
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def run_query(query, params=()):
    with get_conn() as conn:
        return pd.read_sql(query, conn, params=params)

def inicializar_e_migrar():
    conn = get_conn()
    c = conn.cursor()
    # Tabelas
    c.execute("CREATE TABLE IF NOT EXISTS cidades (id INTEGER PRIMARY KEY, nome TEXT, estado TEXT, UNIQUE(nome, estado))")
    c.execute("CREATE TABLE IF NOT EXISTS hospitais (id INTEGER PRIMARY KEY, nome TEXT, cidade_id INTEGER, FOREIGN KEY(cidade_id) REFERENCES cidades(id), UNIQUE(nome, cidade_id))")
    for t in ["distribuidores", "especialistas", "proctors", "operadores"]:
        c.execute(f"CREATE TABLE IF NOT EXISTS {t} (id INTEGER PRIMARY KEY, nome TEXT UNIQUE)")
    
    c.execute("""CREATE TABLE IF NOT EXISTS procedimentos (
            id INTEGER PRIMARY KEY, data_proc DATE, paciente TEXT, idade TEXT, genero TEXT,
            hospital_id INTEGER, distribuidor_id INTEGER, specialist_id INTEGER, proctor_id INTEGER,
            op1_id INTEGER, op2_id INTEGER, report_status TEXT, proctor_form TEXT, overnight_stay TEXT, proctor_eco TEXT,
            team_status TEXT, anatomical_details TEXT, access_type TEXT, offlabel_form_anatomia TEXT, offlabel_form_acesso TEXT,
            myval_size TEXT, sn_protese TEXT, navigator_model TEXT, navigator_lot TEXT, mammoth_model TEXT, mammoth_lot TEXT,
            val_crimp_lot TEXT, phyton_lot TEXT, guidewire TEXT, comentarios TEXT, FOREIGN KEY(hospital_id) REFERENCES hospitais(id))""")
    conn.commit()
    
    # Importação CSV (Lógica mantida resumida)
    try:
        if c.execute("SELECT count(*) FROM procedimentos").fetchone()[0] == 0 and os.path.exists(ARQUIVO_CSV):
            df = pd.read_csv(ARQUIVO_CSV, sep=None, engine='python', dtype=str, encoding='utf-8')
            df.columns = df.columns.str.strip()
            df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x).fillna('')
            
            # Cidades/Hospitais
            for _, r in df[['City', 'State']].drop_duplicates().iterrows():
                if r['City']: c.execute("INSERT OR IGNORE INTO cidades (nome, estado) VALUES (?, ?)", (r['City'], r['State']))
            for _, r in df[['Hospital', 'City', 'State']].drop_duplicates().iterrows():
                if r['Hospital']:
                    res = c.execute("SELECT id FROM cidades WHERE nome=? AND estado=?", (r['City'], r['State'])).fetchone()
                    if res: c.execute("INSERT OR IGNORE INTO hospitais (nome, cidade_id) VALUES (?, ?)", (r['Hospital'], res[0]))
            
            # Pessoas
            mapa = {'Distributor/Meril': 'distribuidores', 'Proctor': 'proctors', 'Specialist / Crimper': 'especialistas', '1st operator': 'operadores', '2st operator': 'operadores'}
            for col, tab in mapa.items():
                if col in df.columns:
                    for val in df[col].unique():
                        if val: c.execute(f"INSERT OR IGNORE INTO {tab} (nome) VALUES (?)", (val,))
            conn.commit()
            
            # Procedimentos
            for _, row in df.iterrows():
                def get_id(tbl, val):
                    r = c.execute(f"SELECT id FROM {tbl} WHERE nome=?", (val,)).fetchone()
                    return r[0] if r else None
                def get_hosp(h, city, uf):
                    r = c.execute("SELECT h.id FROM hospitais h JOIN cidades c ON h.cidade_id=c.id WHERE h.nome=? AND c.nome=? AND c.estado=?", (h, city, uf)).fetchone()
                    return r[0] if r else None
                
                c.execute("""INSERT INTO procedimentos (data_proc, paciente, idade, genero, hospital_id, distribuidor_id, specialist_id, proctor_id, op1_id, op2_id, report_status, proctor_form, overnight_stay, proctor_eco, team_status, anatomical_details, access_type, offlabel_form_anatomia, offlabel_form_acesso, myval_size, sn_protese, navigator_model, navigator_lot, mammoth_model, mammoth_lot, val_crimp_lot, phyton_lot, guidewire, comentarios) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    row.get('Data'), row.get('Patient'), row.get('Age'), row.get('Gender'), get_hosp(row.get('Hospital'), row.get('City'), row.get('State')), get_id('distribuidores', row.get('Distributor/Meril')), get_id('especialistas', row.get('Specialist / Crimper')), get_id('proctors', row.get('Proctor')), get_id('operadores', row.get('1st operator')), get_id('operadores', row.get('2st operator')), row.get('Report'), row.get('Proctor Form'), row.get('Overnight stay'), row.get('Proctor - ECO'), row.get('Team Status'), row.get('Anatomical details'), row.get('Access'), row.get('Offlabel form'), row.get('Offlabel form.1'), row.get('Myval Size'), row.get('SN'), row.get('Navigator'), row.get('Lot'), row.get('Mammoth'), row.get('Lot.1'), row.get('Val de Crimp - Lot'), row.get('Phyton - Lot'), row.get('Guidewire'), row.get('Comments')))
            conn.commit()
    except: pass
    conn.close()

inicializar_e_migrar()

# --- FUNÇÃO GERADORA DE PDF ---
class PDF(FPDF):
    def header(self):
        # Logo
        if os.path.exists(LOGO_FILE):
            self.image(LOGO_FILE, 10, 8, 33)
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 59, 115) # Azul Meril
        self.cell(80)
        self.cell(30, 10, 'Relatório de Procedimento Cirúrgico', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, 'Meril Life Sciences - Surgical Intelligence System | Página ' + str(self.page_no()), 0, 0, 'C')

def gerar_pdf(dados_dict):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Título do Paciente
    pdf.set_fill_color(0, 174, 239) # Azul Ciano
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f" Protocolo #{dados_dict['id']} - Paciente: {dados_dict['paciente']} ({dados_dict['data_proc']})", 0, 1, 'L', fill=True)
    pdf.ln(5)

    # Corpo
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 10)
    
    colunas = [
        ("Hospital", dados_dict['Hospital']), ("Cidade/UF", dados_dict['Cidade'] + "/" + dados_dict['UF']),
        ("Especialista", dados_dict['Especialista']), ("Proctor", dados_dict['Proctor']),
        ("MyVal Size", dados_dict['myval_size']), ("Serial Number", dados_dict['sn_protese']),
        ("Team Status", dados_dict['team_status']), ("Anatomia", dados_dict['anatomical_details'])
    ]
    
    for label, valor in colunas:
        pdf.set_font("Arial", "B", 10)
        pdf.cell(40, 8, label + ":", 0, 0)
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 8, str(valor) if valor else "-")
        
    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, "Comentários Clínicos:", 0, 1)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 6, str(dados_dict['comentarios']) if dados_dict['comentarios'] else "Sem observações adicionais.")
    
    # Salva em memória temporária
    return pdf.output(dest="S").encode("latin-1")

# --- INTERFACE DE LOGIN ---
def login_screen():
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(LOGO_FILE):
            st.image(LOGO_FILE, width=200)
        else:
            st.image(LOGO_URL_BACKUP, width=150)
        
        st.markdown("### Acesso Restrito")
        
        with st.form("login_form"):
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)
            
            if submit:
                if user in USERS and USERS[user]['pass'] == pwd:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = USERS[user]['name']
                    st.session_state['role'] = USERS[user]['role']
                    st.toast(f"Bem-vindo, {USERS[user]['name']}!", icon="👋")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

# --- HELPERS ---
def parse_data(d):
    if not d: return date.today()
    for f in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
        try: return datetime.strptime(d, f).date()
        except: continue
    return date.today()

def load_reg(id):
    df = run_query("SELECT * FROM procedimentos WHERE id = ?", (id,))
    return df.iloc[0] if not df.empty else None

def reset_form():
    st.session_state['registro_atual'] = None
    st.session_state['modo_visualizacao'] = False

# ==============================================================================
# LÓGICA PRINCIPAL DO APP
# ==============================================================================
if not st.session_state['logged_in']:
    login_screen()
else:
    # --- SIDEBAR COM MENU ---
    with st.sidebar:
        if os.path.exists(LOGO_FILE): st.image(LOGO_FILE, width=160)
        else: st.image(LOGO_URL_BACKUP, width=100)
            
        st.markdown(f"Olá, **{st.session_state['username']}**")
        if st.button("Sair / Logout", type="secondary"):
            st.session_state['logged_in'] = False
            st.rerun()
            
        st.divider()
        
        # Menu
        opt_map = {"Dashboard": "📊 Dashboard", "Novo": "📝 Novo Registro", "Consulta": "🔍 Base de Dados", "Admin": "⚙️ Configurações"}
        
        # Bloqueia Admin para usuários comuns
        if st.session_state['role'] != 'admin':
            opt_map.pop("Admin")

        idx_menu = 0
        if st.session_state['pagina_ativa'] in list(opt_map.keys()):
            idx_menu = list(opt_map.keys()).index(st.session_state['pagina_ativa'])

        sel = st.radio("Menu", list(opt_map.keys()), index=idx_menu, format_func=lambda x: opt_map[x], label_visibility="collapsed")
        
        st.divider()
        st.caption("MyVal Enterprise v2.0")

    if sel != st.session_state['pagina_ativa']:
        st.session_state['pagina_ativa'] = sel
        if sel == "Novo" and st.session_state['modo_visualizacao']: reset_form()
        st.rerun()

    # --- DASHBOARD ---
    if st.session_state['pagina_ativa'] == "Dashboard":
        st.title("Business Intelligence")
        
        # Filtro de Data no Dashboard
        c_d1, c_d2 = st.columns(2)
        ini = c_d1.date_input("Data Início", date(2024,1,1))
        fim = c_d2.date_input("Data Fim", date.today())
        
        df = run_query("""
            SELECT p.data_proc, h.nome as hospital, d.nome as distribuidor, p.genero, s.nome as especialista, p.team_status
            FROM procedimentos p
            LEFT JOIN hospitais h ON p.hospital_id = h.id
            LEFT JOIN distribuidores d ON p.distribuidor_id = d.id
            LEFT JOIN especialistas s ON p.specialist_id = s.id
            WHERE p.data_proc BETWEEN ? AND ?
        """, (ini, fim))
        
        if df.empty:
            st.info("Sem dados para o período selecionado.")
        else:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Procedimentos", len(df))
            k2.metric("Hospitais Ativos", df['hospital'].nunique())
            k3.metric("Certificados", len(df[df['team_status']=='Certified']))
            k4.metric("Market Share (Meril)", f"{len(df[df['distribuidor'].str.contains('Meril', na=False, case=False)])}")
            
            st.divider()
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader("Top Hospitais")
                st.bar_chart(df['hospital'].value_counts().head(8), color="#003B73")
            with c2:
                st.subheader("Gênero")
                st.bar_chart(df['genero'].value_counts(), color="#00AEEF")

    # --- NOVO / FORMULÁRIO ---
    elif st.session_state['pagina_ativa'] == "Novo":
        dados = None
        bloq = False
        header = "Novo Procedimento"
        
        if st.session_state['registro_atual']:
            dados = load_reg(st.session_state['registro_atual'])
            if dados is not None:
                bloq = True
                header = f"Registro #{st.session_state['registro_atual']}"
                st.info("🔒 Modo Leitura.")
                if st.button("Novo Cadastro"): reset_form(); st.rerun()

        st.title(header)
        
        # Lookups
        hosp = run_query("SELECT h.id, h.nome, c.nome||'/'||c.estado as loc FROM hospitais h JOIN cidades c ON h.cidade_id=c.id ORDER BY h.nome")
        hosp['l'] = hosp['nome'] + " (" + hosp['loc'] + ")" if not hosp.empty else []
        specs = run_query("SELECT * FROM especialistas ORDER BY nome")
        procs = run_query("SELECT * FROM proctors ORDER BY nome")
        ops = run_query("SELECT * FROM operadores ORDER BY nome")
        dists = run_query("SELECT * FROM distribuidores ORDER BY nome")

        # Helpers Seguros
        def val(k): return dados[k] if (dados is not None and dados[k]) else ""
        def idx(df, c, k): return df[c].tolist().index(int(dados[k])) if (dados is not None and dados[k]) else None
        def idx_l(l, k): return l.index(dados[k]) if (dados is not None and dados[k] in l) else None

        with st.form("meril_form"):
            st.markdown("#### Paciente e Local")
            c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
            v_date = parse_data(dados['data_proc']) if dados is not None else date.today()
            f_dt = c1.date_input("Data", value=v_date, disabled=bloq)
            f_pc = c2.text_input("Iniciais", value=val('paciente'), disabled=bloq)
            f_id = c3.text_input("Idade", value=val('idade'), disabled=bloq)
            f_gn = c4.selectbox("Gênero", ["Male", "Female"], index=idx_l(["Male", "Female"], 'genero'), disabled=bloq)
            
            c5, c6 = st.columns(2)
            f_hp = c5.selectbox("Hospital", hosp['id'], format_func=lambda x: hosp[hosp['id']==x]['l'].values[0] if not hosp.empty else "", index=idx(hosp, 'id', 'hospital_id'), disabled=bloq)
            f_ds = c6.selectbox("Distribuidor", dists['id'], format_func=lambda x: dists[dists['id']==x]['nome'].values[0] if not dists.empty else "", index=idx(dists, 'id', 'distribuidor_id'), disabled=bloq)

            st.markdown("#### Equipe")
            e1, e2, e3 = st.columns(3)
            f_sp = e1.selectbox("Especialista", specs['id'], format_func=lambda x: specs[specs['id']==x]['nome'].values[0], index=idx(specs, 'id', 'specialist_id'), disabled=bloq)
            f_pr = e2.selectbox("Proctor", procs['id'], format_func=lambda x: procs[procs['id']==x]['nome'].values[0], index=idx(procs, 'id', 'proctor_id'), disabled=bloq)
            f_tm = e3.selectbox("Status", ["Certified", "Not Certified", "Proctoring"], index=idx_l(["Certified", "Not Certified", "Proctoring"], 'team_status'), disabled=bloq)
            
            e4, e5 = st.columns(2)
            f_o1 = e4.selectbox("1º Op", ops['id'], format_func=lambda x: ops[ops['id']==x]['nome'].values[0], index=idx(ops, 'id', 'op1_id'), disabled=bloq)
            f_o2 = e5.selectbox("2º Op", ops['id'], format_func=lambda x: ops[ops['id']==x]['nome'].values[0], index=idx(ops, 'id', 'op2_id'), disabled=bloq)

            with st.expander("Detalhes Técnicos", expanded=False):
                cl1, cl2 = st.columns(2)
                f_ac = cl1.text_input("Acesso", value=val('access_type'), disabled=bloq)
                f_an = cl2.text_area("Anatomia", value=val('anatomical_details'), height=70, disabled=bloq)
                
                ck1, ck2 = st.columns(2)
                f_pf = ck1.checkbox("Proctor Form", value=True if val('proctor_form')=="Yes" else False, disabled=bloq)
                f_rp = ck2.text_input("Report Status", value=val('report_status'), disabled=bloq)

            with st.expander("Produtos (Lotes)", expanded=False):
                m1, m2 = st.columns(2)
                f_my = m1.text_input("Myval Size", value=val('myval_size'), disabled=bloq)
                f_sn = m2.text_input("SN Prótese", value=val('sn_protese'), disabled=bloq)
                l1, l2 = st.columns(2)
                f_nl = l1.text_input("Nav Lot", value=val('navigator_lot'), disabled=bloq)
                f_ml = l2.text_input("Mam Lot", value=val('mammoth_lot'), disabled=bloq)
                f_gw = st.text_input("Guidewire", value=val('guidewire'), disabled=bloq)

            f_ob = st.text_area("Comentários", value=val('comentarios'), disabled=bloq)
            
            btn = st.form_submit_button("Salvar Registro", type="primary", disabled=bloq)
            
            if btn and not bloq:
                v_pf = "Yes" if f_pf else "No"
                ok, m = run_action("""INSERT INTO procedimentos (data_proc, paciente, idade, genero, hospital_id, distribuidor_id, specialist_id, proctor_id, op1_id, op2_id, team_status, report_status, proctor_form, access_type, anatomical_details, myval_size, sn_protese, navigator_lot, mammoth_lot, guidewire, comentarios) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                   (f_dt, f_pc, f_id, f_gn, f_hp, f_ds, f_sp, f_pr, f_o1, f_o2, f_tm, f_rp, v_pf, f_ac, f_an, f_my, f_sn, f_nl, f_ml, f_gw, f_ob))
                if ok: st.toast("Salvo!", icon="✅"); time.sleep(1); st.rerun()
                else: st.error(m)

    # --- CONSULTA ---
    elif st.session_state['pagina_ativa'] == "Consulta":
        st.title("Consulta & Relatórios")
        
        # Query mais completa para o PDF
        df = run_query("""
            SELECT p.id, p.data_proc, p.paciente, h.nome as Hospital, c.nome as Cidade, c.estado as UF,
                   s.nome as Especialista, pr.nome as Proctor, p.team_status, p.myval_size, p.sn_protese, p.anatomical_details, p.comentarios
            FROM procedimentos p 
            LEFT JOIN hospitais h ON p.hospital_id = h.id 
            LEFT JOIN cidades c ON h.cidade_id = c.id
            LEFT JOIN especialistas s ON p.specialist_id = s.id 
            LEFT JOIN proctors pr ON p.proctor_id = pr.id
            ORDER BY p.data_proc DESC
        """)
        
        with st.sidebar:
            st.markdown("---")
            st.subheader("Filtros")
            search = st.text_input("Buscar")
            fh = st.multiselect("Hospital", df['Hospital'].dropna().unique())
            fs = st.multiselect("Especialista", df['Especialista'].dropna().unique())
        
        if search: df = df[df['paciente'].str.contains(search, case=False, na=False)]
        if fh: df = df[df['Hospital'].isin(fh)]
        if fs: df = df[df['Especialista'].isin(fs)]
        
        # Display Tabela Resumida
        st.dataframe(df[['id', 'data_proc', 'paciente', 'Hospital', 'Especialista', 'myval_size']], 
                     use_container_width=True, hide_index=True, 
                     column_config={"data_proc": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
        
        st.divider()
        c1, c2, c3 = st.columns([1, 2, 2])
        
        with c1:
            rid = st.selectbox("ID:", df['id'].tolist()) if not df.empty else None
            
        with c2:
            if st.button("👁️ Editar/Ver", disabled=(rid is None)):
                if rid:
                    st.session_state['registro_atual'] = rid
                    st.session_state['modo_visualizacao'] = True
                    st.session_state['pagina_ativa'] = "Novo"
                    st.rerun()
                    
        with c3:
            # Geração de PDF
            if rid:
                reg_pdf = df[df['id'] == rid].iloc[0].to_dict()
                try:
                    pdf_bytes = gerar_pdf(reg_pdf)
                    st.download_button("📄 Baixar PDF Cirúrgico", data=pdf_bytes, file_name=f"Relatorio_{rid}.pdf", mime="application/pdf", type="primary")
                except Exception as e:
                    st.error(f"Erro ao gerar PDF: {e}. Instale fpdf.")

    # --- ADMIN ---
    elif st.session_state['pagina_ativa'] == "Admin":
        st.title("Gestão de Cadastros")
        
        opt = st.selectbox("Tabela", ["Cidades", "Hospitais", "Especialistas", "Proctors", "Operadores"])
        
        if opt == "Cidades":
            with st.form("add_c"):
                nm = st.text_input("Nome")
                uf = st.selectbox("UF", ["SP","RJ","MG","PR","SC","RS","Outros"])
                if st.form_submit_button("Salvar"):
                    run_action("INSERT INTO cidades (nome, estado) VALUES (?,?)", (nm, uf))
                    st.rerun()
            st.dataframe(run_query("SELECT * FROM cidades ORDER BY nome"), hide_index=True)
            
        elif opt == "Hospitais":
            cs = run_query("SELECT id, nome, estado FROM cidades ORDER BY nome")
            with st.form("add_h"):
                nm = st.text_input("Nome")
                cid = st.selectbox("Cidade", cs['id'], format_func=lambda x: f"{cs[cs['id']==x]['nome'].values[0]}")
                if st.form_submit_button("Salvar"):
                    run_action("INSERT INTO hospitais (nome, cidade_id) VALUES (?,?)", (nm, cid))
                    st.rerun()
            st.dataframe(run_query("SELECT h.nome, c.nome as cid FROM hospitais h JOIN cidades c ON h.cidade_id=c.id"), hide_index=True)
            
        else:
            with st.form("add_g"):
                nm = st.text_input("Nome")
                if st.form_submit_button("Salvar"):
                    run_action(f"INSERT INTO {opt.lower()} (nome) VALUES (?)", (nm,))
                    st.rerun()
            st.dataframe(run_query(f"SELECT * FROM {opt.lower()} ORDER BY nome"), hide_index=True)
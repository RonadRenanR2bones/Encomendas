import streamlit as st
import pandas as pd
import sqlite3
import os
import io
import re
from datetime import datetime
import plotly.express as px
from sqlalchemy import create_engine, text

# Configuração da Página
st.set_page_config(
    page_title="R² BONÉS - Controle de Pedidos",
    page_icon="🧢",
    layout="wide"
)

# Senha fixa para o ambiente de Administração
ADMIN_PASSWORD_FIXA = "26210837"

# Estilo CSS customizado
st.markdown('''
<style>
    .status-texto {
        font-weight: bold;
        color: #333333;
    }
    .stDataFrame {
        white-space: nowrap;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        white-space: nowrap !important;
    }
    [data-testid="stDataFrame"] td {
        text-align: left !important;
    }
</style>
''', unsafe_allow_html=True)

# Banco de dados e diretórios
DB_NAME = "ordens_producao.db"
UPLOADS_DIR = "uploads"
COMPROVANTES_DIR = "comprovantes"

if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

if not os.path.exists(COMPROVANTES_DIR):
    os.makedirs(COMPROVANTES_DIR)

# Conexão híbrida: Supabase (PostgreSQL) via Secrets ou SQLite local
@st.cache_resource
def get_db_engine():
    if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
        db_url = st.secrets["postgres"]["url"]
        return create_engine(db_url), "postgres"
    else:
        return None, "sqlite"

engine, db_type = get_db_engine()

def get_db_connection():
    if db_type == "sqlite":
        return sqlite3.connect(DB_NAME)
    return engine

def init_db():
    if db_type == "postgres":
        with engine.begin() as conn:
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS pedidos (
                    id SERIAL PRIMARY KEY,
                    lote_id TEXT,
                    data_criacao TEXT,
                    cor_bone TEXT,
                    frase_arte TEXT,
                    cor_linha TEXT,
                    tipo TEXT,
                    preco REAL,
                    observacoes TEXT,
                    imagem_path TEXT,
                    status TEXT,
                    valor_estampa_extra REAL DEFAULT 0.0,
                    valor_matriz REAL DEFAULT 0.0
                );
            '''))
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS pagamentos (
                    id SERIAL PRIMARY KEY,
                    lote_id TEXT,
                    data_pagamento TEXT,
                    valor_pago REAL,
                    forma_pagamento TEXT,
                    observacoes TEXT,
                    comprovante_path TEXT
                );
            '''))
    else:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lote_id TEXT,
                data_criacao TEXT,
                cor_bone TEXT,
                frase_arte TEXT,
                cor_linha TEXT,
                tipo TEXT,
                preco REAL,
                observacoes TEXT,
                imagem_path TEXT,
                status TEXT,
                valor_estampa_extra REAL DEFAULT 0.0,
                valor_matriz REAL DEFAULT 0.0
            )
        ''')
        c.execute("PRAGMA table_info(pedidos)")
        colunas_pedidos = [column[1] for column in c.fetchall()]
        if "valor_estampa_extra" not in colunas_pedidos:
            c.execute("ALTER TABLE pedidos ADD COLUMN valor_estampa_extra REAL DEFAULT 0.0")
        if "valor_matriz" not in colunas_pedidos:
            c.execute("ALTER TABLE pedidos ADD COLUMN valor_matriz REAL DEFAULT 0.0")

        c.execute("UPDATE pedidos SET tipo = 'Básico' WHERE tipo = 'Simples'")
        c.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lote_id TEXT,
                data_pagamento TEXT,
                valor_pago REAL,
                forma_pagamento TEXT,
                observacoes TEXT,
                comprovante_path TEXT
            )
        ''')
        c.execute("UPDATE pedidos SET status = 'Em Produção' WHERE status = 'Pendente'")
        conn.commit()
        conn.close()

def deletar_item(item_id):
    if db_type == "postgres":
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM pedidos WHERE id = :id"), {"id": item_id})
    else:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT imagem_path FROM pedidos WHERE id = ?", (item_id,))
        res = c.fetchone()
        if res and res[0] and os.path.exists(res[0]):
            try:
                os.remove(res[0])
            except Exception:
                pass
        c.execute("DELETE FROM pedidos WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

def deletar_pagamento(pagamento_id):
    if db_type == "postgres":
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM pagamentos WHERE id = :id"), {"id": pagamento_id})
    else:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT comprovante_path FROM pagamentos WHERE id = ?", (pagamento_id,))
        res = c.fetchone()
        if res and res[0] and os.path.exists(res[0]):
            try:
                os.remove(res[0])
            except Exception:
                pass
        c.execute("DELETE FROM pagamentos WHERE id = ?", (pagamento_id,))
        conn.commit()
        conn.close()

def carregar_dataframe(query, params=None):
    if db_type == "postgres":
        return pd.read_sql_query(text(query), engine, params=params)
    else:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

def clean_currency(val):
    if pd.isna(val) or str(val).strip() in ["-", "", "nan"]:
        return 0.0
    val_str = str(val).replace("R$", "").strip()
    if "," in val_str:
        val_str = val_str.replace(".", "").replace(",", ".")
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def gerar_excel_expandido(df):
    try:
        import openpyxl
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Pedidos')
            worksheet = writer.sheets['Pedidos']
            for col in worksheet.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    val_str = str(cell.value or '')
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                    cell.alignment = cell.alignment.copy(wrap_text=False)
                worksheet.column_dimensions[col_letter].width = max(max_len + 5, 12)
        output.seek(0)
        return output, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    except ImportError:
        output = io.BytesIO()
        csv_bytes = df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
        output.write(csv_bytes)
        output.seek(0)
        return output, "text/csv", "csv"

# Modais
@st.dialog("🔍 Buscar e Selecionar Pedido")
def modal_buscar_pedido(key_prefix, lista_lotes):
    st.write("Digite o nome ou número do pedido para filtrar:")
    termo = st.text_input("Buscar por Nome:", key=f"search_{key_prefix}")
    lotes_filtrados = [l for l in lista_lotes if termo.lower() in str(l).lower()] if termo else lista_lotes
    if lotes_filtrados:
        selecionado = st.radio("Selecione o pedido na lista:", lotes_filtrados, key=f"radio_{key_prefix}")
        if st.button("Confirmar Seleção", key=f"btn_confirm_{key_prefix}", use_container_width=True):
            st.session_state[f"selected_lote_{key_prefix}"] = selecionado
            st.rerun()
    else:
        st.warning("Nenhum pedido encontrado com este termo.")

@st.dialog("📸 Foto de Referência da Estampa")
def modal_visualizar_foto(img_path, nome_arte):
    if img_path and os.path.exists(img_path):
        st.image(img_path, use_container_width=True, caption=f"Arte: {nome_arte}")
    else:
        st.warning("⚠️ Foto de referência não encontrada ou indisponível.")

@st.dialog("🔍 Detalhes dos Itens Extras")
def modal_detalhes_extra(titulo, df_detalhes, coluna_valor):
    st.markdown(f"### {titulo}")
    df_view = df_detalhes[["cor_bone", "frase_arte", "cor_linha", coluna_valor]].copy()
    df_view[coluna_valor] = df_view[coluna_valor].apply(lambda x: f"R$ {x:.2f}")
    nome_col_val = "Valor Extra" if coluna_valor == "valor_estampa_extra" else "Valor Matriz"
    df_view = df_view.rename(columns={
        "cor_bone": "Cor do Boné",
        "frase_arte": "Arte",
        "cor_linha": "Cor da Estampa",
        coluna_valor: nome_col_val
    })
    st.dataframe(df_view, use_container_width=True, hide_index=True)

init_db()

# Título Principal
st.title("🧢 R² BONÉS - Controle de Pedidos")

# Controle de Acesso ADM
st.sidebar.header("👤 Perfil de Acesso")
perfil = st.sidebar.selectbox("Acessar como:", ["Ateliê", "R2 Bonés"])

is_admin = False
if perfil == "R2 Bonés":
    if "admin_autenticado" not in st.session_state:
        st.session_state["admin_autenticado"] = False
    if not st.session_state["admin_autenticado"]:
        senha_digitada = st.sidebar.text_input("Digite a Senha de ADM:", type="password", key="senha_input_adm")
        if senha_digitada == ADMIN_PASSWORD_FIXA:
            st.session_state["admin_autenticado"] = True
            st.rerun()
        elif senha_digitada != "":
            st.sidebar.error("❌ Senha incorreta!")
    else:
        is_admin = True
        st.sidebar.success("🔒 Acesso ADM Liberado")
else:
    st.session_state["admin_autenticado"] = False

# NAVEGAÇÃO (Aba Importação visível APENAS para ADM)
if is_admin:
    menu_options = ["➕ Encomenda", "📥 Importar Excel", "📋 Produção", "📊 Tabela Geral", "💰 Financeiro", "📈 Dashboard ADM"]
else:
    menu_options = ["📋 Produção", "📊 Tabela Geral", "💰 Financeiro"]

menu = st.sidebar.radio("", menu_options, label_visibility="collapsed")

# Gestão de Banco na Sidebar (Apenas ADM)
if is_admin and db_type == "sqlite":
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Gestão do Banco de Dados")
    uploaded_db = st.sidebar.file_uploader("📥 Importar / Restaurar Banco (.db)", type=["db", "sqlite", "sqlite3"], key="uploader_db_sidebar")
    if uploaded_db is not None:
        with open(DB_NAME, "wb") as f:
            f.write(uploaded_db.getbuffer())
        st.sidebar.success("✅ Banco atualizado com sucesso!")
        st.rerun()
    if os.path.exists(DB_NAME):
        with open(DB_NAME, "rb") as f_db:
            st.sidebar.download_button(
                label="📤 Baixar Backup Atual (.db)",
                data=f_db,
                file_name="ordens_producao.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )

STATUS_OPCOES = ["Em Produção", "Concluído", "Entregue / Retirado"]

# -------------------------------------------------------------
# ROTINA EXCLUSIVA ADM: IMPORTAÇÃO DE PEDIDOS EM EXCEL
# -------------------------------------------------------------
if menu == "📥 Importar Excel" and is_admin:
    st.header("📥 Importar Pedidos de Ficheiros Excel (.xlsx)")
    st.write("Selecione um ou vários ficheiros Excel de pedidos para importar todos os itens automaticamente para o sistema.")

    uploaded_files = st.file_uploader(
        "Carregar Ficheiros de Pedidos (.xlsx)", 
        type=["xlsx", "xls"], 
        accept_multiple_files=True,
        key="uploader_excel_pedidos"
    )

    if uploaded_files:
        st.markdown("---")
        st.subheader("📋 Pré-visualização dos Pedidos Encontrados")
        
        registos_para_importar = []
        
        for file in uploaded_files:
            nome_arquivo = file.name
            # Extrai o Lote ID ex: 'Pedido_#1.10-2026.xlsx' -> '#1.10/2026'
            lote_sugerido = nome_arquivo.replace("Pedido_", "").replace(".xlsx", "").replace(".xls", "").replace("-", "/")
            
            try:
                df_excel = pd.read_excel(file)
                st.write(f"📁 **Ficheiro:** `{nome_arquivo}` | **Pedido Identificado:** `{lote_sugerido}` | **Total de itens:** {len(df_excel)}")
                
                for _, row in df_excel.iterrows():
                    data_raw = row.get('Data', datetime.now().strftime("%d/%m/%Y"))
                    data_fmt = str(data_raw).split(" ")[0] if pd.notna(data_raw) else datetime.now().strftime("%d/%m/%Y")
                    
                    item = {
                        "lote_id": lote_sugerido,
                        "data_criacao": data_fmt,
                        "cor_bone": str(row.get('Cor do Boné', '')).strip() if pd.notna(row.get('Cor do Boné')) else '',
                        "frase_arte": str(row.get('Arte Estampada', '')).strip() if pd.notna(row.get('Arte Estampada')) else '',
                        "cor_linha": str(row.get('Cor da Estampa', '')).strip() if pd.notna(row.get('Cor da Estampa')) else '',
                        "tipo": str(row.get('Produto', 'Básico')).strip() if pd.notna(row.get('Produto')) else 'Básico',
                        "preco": clean_currency(row.get('Preço Base', 29.0)),
                        "valor_estampa_extra": clean_currency(row.get('Estampa Extra', 0.0)),
                        "valor_matriz": clean_currency(row.get('Matriz Bordado', 0.0)),
                        "status": str(row.get('Status', 'Em Produção')).strip() if pd.notna(row.get('Status')) else 'Em Produção',
                        "observacoes": str(row.get('Observações', '')).strip() if pd.notna(row.get('Observações')) else '',
                        "imagem_path": ""
                    }
                    registos_para_importar.append(item)
            except Exception as e:
                st.error(f"Erro ao ler o ficheiro '{nome_arquivo}': {e}")

        if registos_para_importar:
            df_preview = pd.DataFrame(registos_para_importar)
            st.dataframe(
                df_preview[["lote_id", "data_criacao", "cor_bone", "frase_arte", "cor_linha", "tipo", "preco", "valor_estampa_extra", "valor_matriz", "status"]], 
                use_container_width=True, 
                hide_index=True
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Confirmar e Gravar Pedidos no Banco de Dados", type="primary", use_container_width=True):
                qtd_sucesso = 0
                if db_type == "postgres":
                    with engine.begin() as conn:
                        for r in registos_para_importar:
                            conn.execute(text('''
                                INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, imagem_path, status, valor_estampa_extra, valor_matriz)
                                VALUES (:lote_id, :data_criacao, :cor_bone, :frase_arte, :cor_linha, :tipo, :preco, :observacoes, :imagem_path, :status, :valor_estampa_extra, :valor_matriz)
                            '''), r)
                            qtd_sucesso += 1
                else:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    for r in registos_para_importar:
                        c.execute('''
                            INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, imagem_path, status, valor_estampa_extra, valor_matriz)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (r['lote_id'], r['data_criacao'], r['cor_bone'], r['frase_arte'], r['cor_linha'], r['tipo'], r['preco'], r['observacoes'], r['imagem_path'], r['status'], r['valor_estampa_extra'], r['valor_matriz']))
                        qtd_sucesso += 1
                    conn.commit()
                    conn.close()
                
                st.balloons()
                st.success(f"🎉 Importação concluída com sucesso! {qtd_sucesso} bonés foram cadastrados no sistema.")

# -------------------------------------------------------------
# 1. TELA DE ENCOMENDA (ADMINISTRADOR / R2 BONÉS)
# -------------------------------------------------------------
elif menu == "➕ Encomenda" and is_admin:
    st.header("Cadastrar Item na Encomenda")
    st.write("Selecione um lote/pedido existente ou crie um novo para vincular os bonés.")

    df_lotes_db = carregar_dataframe("SELECT DISTINCT lote_id FROM pedidos WHERE lote_id IS NOT NULL AND lote_id != '' ORDER BY id DESC")
    lotes_existentes = list(df_lotes_db["lote_id"].unique()) if not df_lotes_db.empty else []

    if "selected_lote_encomenda" not in st.session_state and lotes_existentes:
        st.session_state["selected_lote_encomenda"] = lotes_existentes[0]

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        opcao_lote = st.radio("Pedido:", ["Consulta Pedido", "Novo Pedido"], horizontal=True)
        if opcao_lote == "Consulta Pedido" and lotes_existentes:
            c_sel, c_btn = st.columns([3, 1])
            with c_sel:
                nome_lote = st.selectbox(
                    "Consultar Pedido", 
                    lotes_existentes, 
                    index=lotes_existentes.index(st.session_state["selected_lote_encomenda"]) if st.session_state["selected_lote_encomenda"] in lotes_existentes else 0
                )
                st.session_state["selected_lote_encomenda"] = nome_lote
            with c_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔍", key="btn_lupa_encomenda", help="Abrir busca suspensa por nome"):
                    modal_buscar_pedido("encomenda", lotes_existentes)
        else:
            nome_lote_padrao = datetime.now().strftime("%d/%m/%Y")
            nome_lote = st.text_input("Nome do Novo Pedido:", value=nome_lote_padrao, help="Ex: 01/10/2026, Pedido Feirarte")

    with col_l2:
        st.info(f"📍 **Pedido Selecionado:** `{nome_lote}`")

    st.markdown("---")
    st.subheader("Detalhes do Boné Individual")

    with st.form("form_item_lote", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cor_bone = st.text_input("Cor do Boné", placeholder="Ex: Off White, Caramelo, Rosa Claro, Cinza")
            frase_arte = st.text_area("Arte Estampada", placeholder="Ex: Cariocando (com onda centralizada embaixo)")
            cor_linha = st.text_input("Cor da Estampa", placeholder="Ex: Azul, Preto, Off White, Bordô")
            uploaded_file = st.file_uploader("Foto / Imagem de Referência da Estampa (Opcional)", type=["jpg", "jpeg", "png", "webp"])

        with col2:
            tipo = st.selectbox("Produto", ["Básico", "Premium", "Kids", "Outro"])
            preco_str = st.text_input("Preço Unitário (R$)", value="29,00")
            estampa_extra_str = st.text_input("Estampa Extra (R$)", value="0,00", help="Valor adicional para estampa extra (opcional)")
            matriz_str = st.text_input("Taxa Matriz de Bordado (R$)", value="0,00", help="Taxa pontual para criação/ajuste técnico de matriz (opcional)")
            observacoes = st.text_input("Observações Específicas", placeholder="Ex: Bordado frontal 12cm, fonte manuscrita")
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("➕ Adicionar Boné à Encomenda", use_container_width=True)

        if submit:
            preco_val = clean_currency(preco_str) or 29.0
            estampa_extra_val = clean_currency(estampa_extra_str)
            matriz_val = clean_currency(matriz_str)

            if not cor_bone or not frase_arte:
                st.error("Por favor, preencha a cor do boné e a arte estampada.")
            else:
                img_path = ""
                if uploaded_file is not None:
                    file_ext = uploaded_file.name.split(".")[-1]
                    filename = f"ref_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.{file_ext}"
                    img_path = os.path.join(UPLOADS_DIR, filename)
                    with open(img_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                data_atual = datetime.now().strftime("%d/%m/%Y")
                if db_type == "postgres":
                    with engine.begin() as conn:
                        conn.execute(text('''
                            INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, imagem_path, status, valor_estampa_extra, valor_matriz)
                            VALUES (:lote_id, :data_criacao, :cor_bone, :frase_arte, :cor_linha, :tipo, :preco, :observacoes, :imagem_path, 'Em Produção', :valor_estampa_extra, :valor_matriz)
                        '''), {
                            "lote_id": nome_lote, "data_criacao": data_atual, "cor_bone": cor_bone,
                            "frase_arte": frase_arte, "cor_linha": cor_linha, "tipo": tipo,
                            "preco": preco_val, "observacoes": observacoes, "imagem_path": img_path,
                            "valor_estampa_extra": estampa_extra_val, "valor_matriz": matriz_val
                        })
                else:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, imagem_path, status, valor_estampa_extra, valor_matriz)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Em Produção', ?, ?)
                    ''', (nome_lote, data_atual, cor_bone, frase_arte, cor_linha, tipo, preco_val, observacoes, img_path, estampa_extra_val, matriz_val))
                    conn.commit()
                    conn.close()

                st.success(f"✅ Boné '{frase_arte}' adicionado com sucesso ao pedido '{nome_lote}'!")
                st.rerun()

    st.markdown("---")
    st.subheader(f"📦 Resumo da Produção Pedido '{nome_lote}'")
    
    if db_type == "postgres":
        df_lote_atual = carregar_dataframe("SELECT *, (preco + COALESCE(valor_estampa_extra, 0) + COALESCE(valor_matriz, 0)) as preco_total FROM pedidos WHERE lote_id = :lote ORDER BY id DESC", params={"lote": nome_lote})
    else:
        df_lote_atual = carregar_dataframe("SELECT *, (preco + COALESCE(valor_estampa_extra, 0) + COALESCE(valor_matriz, 0)) as preco_total FROM pedidos WHERE lote_id = ? ORDER BY id DESC", params=(nome_lote,))

    if not df_lote_atual.empty:
        df_exibicao = df_lote_atual.copy()
        df_exibicao["Preço Base"] = df_exibicao["preco"].apply(lambda x: f"R$ {x:.2f}")
        df_exibicao["Preço Total"] = df_exibicao["preco_total"].apply(lambda x: f"R$ {x:.2f}")

        cols_para_exibir = ["cor_bone", "frase_arte"]
        if df_exibicao["cor_linha"].dropna().astype(str).str.strip().ne("").any():
            cols_para_exibir.append("cor_linha")
        cols_para_exibir.append("tipo")
        cols_para_exibir.append("Preço Base")

        if (df_exibicao["valor_estampa_extra"] > 0).any():
            df_exibicao["Estampa Extra"] = df_exibicao["valor_estampa_extra"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
            cols_para_exibir.append("Estampa Extra")

        if (df_exibicao["valor_matriz"] > 0).any():
            df_exibicao["Matriz Bordado"] = df_exibicao["valor_matriz"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
            cols_para_exibir.append("Matriz Bordado")

        cols_para_exibir.extend(["Preço Total", "status"])
        if df_exibicao["observacoes"].dropna().astype(str).str.strip().ne("").any():
            cols_para_exibir.append("observacoes")

        df_display = df_exibicao[cols_para_exibir].rename(columns={
            "cor_bone": "Cor do Boné",
            "frase_arte": "Arte Estampada",
            "cor_linha": "Cor da Estampa",
            "tipo": "Produto",
            "status": "Status",
            "observacoes": "Observações"
        })
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        col_del_a, col_del_b = st.columns([3, 1])
        with col_del_a:
            dict_itens = {row["id"]: f"{row['cor_bone']} - {row['frase_arte']} ({row['cor_linha']})" for _, row in df_lote_atual.iterrows()}
            id_selecionado = st.selectbox("Selecione o item para remover:", options=list(dict_itens.keys()), format_func=lambda x: dict_itens[x])
        with col_del_b:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("❌ Excluir Item", key="btn_del_encomenda"):
                deletar_item(id_selecionado)
                st.success("Item excluído com sucesso!")
                st.rerun()

        total_pedido_soma = df_lote_atual['preco_total'].sum()
        st.markdown("---")
        st.write(f"**Total de itens neste pedido:** {len(df_lote_atual)} boné(s) | **Valor Total do Pedido:** R$ {total_pedido_soma:.2f}")

# -------------------------------------------------------------
# 2. TELA DE PRODUÇÃO
# -------------------------------------------------------------
elif menu == "📋 Produção":
    st.header("📋 Produção")
    df = carregar_dataframe("SELECT * FROM pedidos ORDER BY id DESC")

    if df.empty:
        st.info("Nenhum pedido cadastrado até o momento.")
    else:
        col_f1, col_f2 = st.columns(2)
        lotes_ordenados = list(df["lote_id"].dropna().unique())
        lotes_disponiveis = ["Todos"] + lotes_ordenados
        lote_padrao = lotes_ordenados[0] if lotes_ordenados else "Todos"

        if "selected_lote_prod" not in st.session_state:
            st.session_state["selected_lote_prod"] = lote_padrao

        with col_f1:
            c_prod_sel, c_prod_btn = st.columns([3, 1])
            with c_prod_sel:
                lote_filter = st.selectbox(
                    "Filtrar por Lote / Encomenda", 
                    lotes_disponiveis,
                    index=lotes_disponiveis.index(st.session_state["selected_lote_prod"]) if st.session_state["selected_lote_prod"] in lotes_disponiveis else 0
                )
                st.session_state["selected_lote_prod"] = lote_filter
            with c_prod_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔍", key="btn_lupa_producao", help="Abrir busca suspensa por nome"):
                    modal_buscar_pedido("prod", lotes_disponiveis)

        with col_f2:
            status_filter = st.multiselect("Filtrar por Status", options=STATUS_OPCOES, default=["Em Produção", "Concluído"])

        if status_filter:
            df = df[df["status"].isin(status_filter)]
        if lote_filter != "Todos":
            df = df[df["lote_id"] == lote_filter]

        st.caption(f"Exibindo {len(df)} boné(s)")

        for idx, row in df.iterrows():
            with st.container():
                st.markdown("---")
                col_info, col_status = st.columns([2.5, 1])
                
                with col_info:
                    if row["lote_id"]:
                        st.markdown(f"📦 **Pedido:** `{row['lote_id']}`")
                    st.markdown(f"**Cor do Boné:** `{row['cor_bone'] or '-'}`")
                    st.markdown(f"**Arte Estampada:** `{row['frase_arte'] or '-'}`")
                    st.markdown(f"**Cor da Estampa:** `{row['cor_linha'] or '-'}`")
                    st.markdown(f"**Produto:** `{row['tipo']}`")
                    
                    if row.get("valor_estampa_extra", 0) > 0:
                        st.markdown(f"**Estampa Extra:** `R$ {row['valor_estampa_extra']:.2f}`")
                    if row.get("valor_matriz", 0) > 0:
                        st.markdown(f"**Taxa Matriz de Bordado:** `R$ {row['valor_matriz']:.2f}`")

                    if row["imagem_path"] and os.path.exists(row["imagem_path"]):
                        c_ref_lbl, c_ref_btn = st.columns([1.1, 1])
                        with c_ref_lbl:
                            st.write("**Foto de Referência:**")
                        with c_ref_btn:
                            if st.button("📸 Ver Foto", key=f"btn_pop_img_{row['id']}"):
                                modal_visualizar_foto(row["imagem_path"], row["frase_arte"])
                    else:
                        st.markdown("**Foto de Referência:** `Sem foto cadastrada`")

                    if row["observacoes"]:
                        st.info(f"📌 **Obs:** {row['observacoes']}")
                        
                with col_status:
                    data_so_data = str(row['data_criacao']).split(" ")[0] if row['data_criacao'] else ""
                    st.write(f"**Data:** {data_so_data}")
                    st.markdown(f"**Status Atual:** **{row['status']}**")
                    
                    idx_st = STATUS_OPCOES.index(row["status"]) if row["status"] in STATUS_OPCOES else 0
                    novo_status = st.selectbox("Atualizar Status", STATUS_OPCOES, index=idx_st, key=f"status_{row['id']}")
                    if novo_status != row["status"]:
                        if db_type == "postgres":
                            with engine.begin() as conn:
                                conn.execute(text("UPDATE pedidos SET status = :status WHERE id = :id"), {"status": novo_status, "id": row['id']})
                        else:
                            conn = sqlite3.connect(DB_NAME)
                            c = conn.cursor()
                            c.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo_status, row['id']))
                            conn.commit()
                            conn.close()
                        st.rerun()

                    if is_admin:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🗑 Excluir Item", key=f"btn_del_card_{row['id']}"):
                            deletar_item(row['id'])
                            st.success("Item excluído!")
                            st.rerun()

# -------------------------------------------------------------
# 3. TABELA GERAL (EXPORTAÇÃO POR PEDIDO)
# -------------------------------------------------------------
elif menu == "📊 Tabela Geral":
    st.header("📊 Tabela Geral de Pedidos")
    df = carregar_dataframe("SELECT id, lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, valor_estampa_extra, valor_matriz, status, observacoes FROM pedidos ORDER BY id DESC")

    if df.empty:
        st.info("Nenhum pedido cadastrado.")
    else:
        df['lote_id'] = df['lote_id'].fillna('Sem Lote Definido')
        df['total_item'] = df['preco'] + df['valor_estampa_extra'].fillna(0) + df['valor_matriz'].fillna(0)
        lotes_unicos = df['lote_id'].unique()

        for lote in lotes_unicos:
            df_lote = df[df['lote_id'] == lote].copy()
            total_qtd = len(df_lote)
            total_valor = df_lote['total_item'].sum()
            
            with st.expander(f"📦 Pedido: {lote} — ({total_qtd} bonés | Total: R$ {total_valor:.2f})", expanded=False):
                df_lote["Preço Base"] = df_lote["preco"].apply(lambda x: f"R$ {x:.2f}")
                df_lote["Total Item"] = df_lote["total_item"].apply(lambda x: f"R$ {x:.2f}")
                df_lote["Data"] = df_lote["data_criacao"].apply(lambda x: str(x).split(" ")[0] if x else "")
                
                cols_lote = ["cor_bone", "frase_arte"]
                if df_lote["cor_linha"].dropna().astype(str).str.strip().ne("").any():
                    cols_lote.append("cor_linha")
                cols_lote.append("tipo")
                cols_lote.append("Preço Base")
                
                if (df_lote["valor_estampa_extra"] > 0).any():
                    df_lote["Estampa Extra"] = df_lote["valor_estampa_extra"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
                    cols_lote.append("Estampa Extra")
                if (df_lote["valor_matriz"] > 0).any():
                    df_lote["Matriz Bordado"] = df_lote["valor_matriz"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
                    cols_lote.append("Matriz Bordado")
                    
                cols_lote.extend(["Total Item", "status"])
                if df_lote["observacoes"].dropna().astype(str).str.strip().ne("").any():
                    cols_lote.append("observacoes")
                cols_lote.append("Data")

                df_exibicao_lote = df_lote[cols_lote].rename(columns={
                    "cor_bone": "Cor do Boné",
                    "frase_arte": "Arte Estampada",
                    "cor_linha": "Cor da Estampa",
                    "tipo": "Produto",
                    "status": "Status",
                    "observacoes": "Observações"
                })
                
                if is_admin:
                    col_t, col_d = st.columns([4, 1])
                    with col_t:
                        st.dataframe(df_exibicao_lote, use_container_width=True, hide_index=True)
                    with col_d:
                        st.markdown("##### 🗑 Excluir Item")
                        dict_itens_tbl = {row["id"]: f"{row['cor_bone']} - {row['frase_arte']}" for _, row in df_lote.iterrows()}
                        id_del = st.selectbox("Item:", options=list(dict_itens_tbl.keys()), format_func=lambda x: dict_itens_tbl[x], key=f"sel_tbl_{lote}")
                        if st.button("❌ Excluir", key=f"btn_del_tbl_{lote}"):
                            deletar_item(id_del)
                            st.success("Item excluído!")
                            st.rerun()
                else:
                    st.dataframe(df_exibicao_lote, use_container_width=True, hide_index=True)

                st.markdown("<br>", unsafe_allow_html=True)
                excel_lote_bytes, mime_lote, ext_lote = gerar_excel_expandido(df_exibicao_lote)
                lote_filename = str(lote).replace('/', '-').replace(' ', '_')
                st.download_button(
                    label=f"📥 Exportar Pedido '{lote}' em Excel",
                    data=excel_lote_bytes,
                    file_name=f"Pedido_{lote_filename}.{ext_lote}",
                    mime=mime_lote,
                    key=f"btn_exp_lote_{lote}"
                )

# -------------------------------------------------------------
# 4. TELA FINANCEIRO
# -------------------------------------------------------------
elif menu == "💰 Financeiro":
    st.header("💰 Controle Financeiro de Pedidos")
    st.write("Acompanhamento de pagamentos por pedido (adiantamentos e quitações).")

    df_pedidos = carregar_dataframe("SELECT lote_id, SUM(preco + COALESCE(valor_estampa_extra, 0) + COALESCE(valor_matriz, 0)) as total_pedido FROM pedidos WHERE lote_id IS NOT NULL AND lote_id != '' GROUP BY lote_id ORDER BY min(id) DESC")
    df_todos_itens = carregar_dataframe("SELECT lote_id, cor_bone, frase_arte, cor_linha, tipo, preco, COALESCE(valor_estampa_extra, 0) as valor_estampa_extra, COALESCE(valor_matriz, 0) as valor_matriz FROM pedidos WHERE lote_id IS NOT NULL AND lote_id != ''")
    df_pagamentos = carregar_dataframe("SELECT * FROM pagamentos ORDER BY id DESC")

    if df_pedidos.empty:
        st.info("Nenhum pedido cadastrado para exibir no controle financeiro.")
    else:
        lotes_list = list(df_pedidos["lote_id"].unique())

        if is_admin:
            with st.expander("➕ **Registrar Novo Pagamento (Exclusivo ADM)**", expanded=True):
                with st.form("form_pagamento", clear_on_submit=True):
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        if "selected_lote_fin" not in st.session_state:
                            st.session_state["selected_lote_fin"] = lotes_list[0]
                        lote_pag = st.selectbox(
                            "Selecione o Pedido:", 
                            lotes_list,
                            index=lotes_list.index(st.session_state["selected_lote_fin"]) if st.session_state["selected_lote_fin"] in lotes_list else 0
                        )
                        st.session_state["selected_lote_fin"] = lote_pag
                        row_pedido = df_pedidos[df_pedidos["lote_id"] == lote_pag]
                        val_total = row_pedido["total_pedido"].values[0] if not row_pedido.empty else 0.0
                        st.caption(f"Valor Total do Pedido: **R$ {val_total:.2f}**")
                    
                    with col_p2:
                        valor_pago_str = st.text_input("Valor Pago (R$)", value="", placeholder="Digite o valor pago")
                        forma_pag = st.selectbox("Forma de Pagamento", ["Pix", "Cartão de Crédito"])

                    with col_p3:
                        data_pag = st.date_input("Data do Pagamento", value=datetime.now())
                        obs_pag = st.text_input("Observação", placeholder="Ex: Entrada, Sinal, Quitação final")
                        uploaded_comp = st.file_uploader("Comprovante de Pagamento (Opcional)", type=["jpg", "jpeg", "png", "pdf"])

                    submit_pag = st.form_submit_button("💳 Registrar Pagamento", use_container_width=True)

                    if submit_pag:
                        val_pago_num = clean_currency(valor_pago_str)
                        if val_pago_num <= 0:
                            st.error("Insira um valor pago válido.")
                        else:
                            comp_path = ""
                            if uploaded_comp is not None:
                                file_ext = uploaded_comp.name.split(".")[-1]
                                filename_comp = f"comp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.{file_ext}"
                                comp_path = os.path.join(COMPROVANTES_DIR, filename_comp)
                                with open(comp_path, "wb") as f:
                                    f.write(uploaded_comp.getbuffer())

                            data_pag_str = data_pag.strftime("%d/%m/%Y")
                            if db_type == "postgres":
                                with engine.begin() as conn:
                                    conn.execute(text('''
                                        INSERT INTO pagamentos (lote_id, data_pagamento, valor_pago, forma_pagamento, observacoes, comprovante_path)
                                        VALUES (:lote_id, :data_pagamento, :valor_pago, :forma_pagamento, :observacoes, :comprovante_path)
                                    '''), {
                                        "lote_id": lote_pag, "data_pagamento": data_pag_str,
                                        "valor_pago": val_pago_num, "forma_pagamento": forma_pag,
                                        "observacoes": obs_pag, "comprovante_path": comp_path
                                    })
                            else:
                                conn = sqlite3.connect(DB_NAME)
                                c = conn.cursor()
                                c.execute('''
                                    INSERT INTO pagamentos (lote_id, data_pagamento, valor_pago, forma_pagamento, observacoes, comprovante_path)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                ''', (lote_pag, data_pag_str, val_pago_num, forma_pag, obs_pag, comp_path))
                                conn.commit()
                                conn.close()
                            
                            st.success(f"✅ Pagamento de R$ {val_pago_num:.2f} registrado para o pedido '{lote_pag}'!")
                            st.rerun()

        st.markdown("---")
        st.subheader("📊 Resumo Financeiro por Pedido")

        for _, row in df_pedidos.iterrows():
            lote = row["lote_id"]
            total_pedido = row["total_pedido"]

            df_pag_lote = df_pagamentos[df_pagamentos["lote_id"] == lote] if not df_pagamentos.empty else pd.DataFrame()
            total_pago = df_pag_lote["valor_pago"].sum() if not df_pag_lote.empty else 0.0
            saldo_devedor = total_pedido - total_pago

            if total_pago >= total_pedido and total_pedido > 0:
                status_pag = "🟢 Pago (100%)"
            elif total_pago > 0:
                pct = (total_pago / total_pedido) * 100 if total_pedido > 0 else 0
                status_pag = f"🟡 Parcial ({pct:.0f}%)"
            else:
                status_pag = "🔴 Pendente"

            with st.expander(f"📦 Pedido: {lote} | Status: {status_pag}", expanded=False):
                c_m1, c_m2, c_m3, c_m4 = st.columns(4)
                c_m1.metric("Total do Pedido", f"R$ {total_pedido:.2f}")
                c_m2.metric("Total Pago", f"R$ {total_pago:.2f}")
                c_m3.metric("Saldo Restante", f"R$ {max(saldo_devedor, 0.0):.2f}")
                c_m4.metric("Status do Pagamento", status_pag)

                st.markdown("##### Histórico de Pagamentos")
                if not df_pag_lote.empty:
                    for _, p_row in df_pag_lote.iterrows():
                        col_p_info, col_p_comp, col_p_act = st.columns([4.2, 1.2, 0.8])
                        with col_p_info:
                            obs_texto = f" {p_row['observacoes']}" if p_row['observacoes'] else " Sem observação"
                            st.markdown(f"🗓 **Data:** {p_row['data_pagamento']} | 💰 **Valor:** R$ {p_row['valor_pago']:.2f} | 💳 **Forma:** {p_row['forma_pagamento']} | 📌 **Obs:**{obs_texto}")
                        with col_p_comp:
                            c_path = p_row.get("comprovante_path")
                            if c_path and os.path.exists(str(c_path)):
                                with open(c_path, "rb") as file_bytes:
                                    st.download_button(
                                        label="📎 Comprovante",
                                        data=file_bytes,
                                        file_name=os.path.basename(c_path),
                                        key=f"dl_comp_{p_row['id']}"
                                    )
                            else:
                                st.caption("Sem comprovante")
                        with col_p_act:
                            if is_admin:
                                if st.button("❌ Excluir", key=f"btn_del_pag_{p_row['id']}"):
                                    deletar_pagamento(p_row['id'])
                                    st.success("Pagamento removido!")
                                    st.rerun()
                else:
                    st.caption("Nenhum pagamento registrado para este pedido ainda.")

                st.markdown("##### 🧢 Detalhamento")
                df_itens_lote = df_todos_itens[df_todos_itens["lote_id"] == lote]
                
                if not df_itens_lote.empty:
                    col_det1, col_det2 = st.columns(2)
                    with col_det1:
                        st.markdown("**Bonés**")
                        counts_prod = df_itens_lote.groupby("tipo").size().reset_index(name="Quantidade")
                        counts_prod = counts_prod.rename(columns={"tipo": "Produto"})
                        counts_prod["Quantidade"] = counts_prod["Quantidade"].astype(str)
                        st.dataframe(counts_prod, use_container_width=True, hide_index=True)

                    with col_det2:
                        df_estampas = df_itens_lote[df_itens_lote["valor_estampa_extra"] > 0]
                        df_matrizes = df_itens_lote[df_itens_lote["valor_matriz"] > 0]
                        has_extras = not df_estampas.empty or not df_matrizes.empty
                        
                        if has_extras:
                            st.markdown("**Extras**")
                            extras_lista = []
                            if not df_estampas.empty:
                                extras_lista.append({"Produto": "Estampa", "Quantidade": str(len(df_estampas))})
                            if not df_matrizes.empty:
                                extras_lista.append({"Produto": "Matriz de Bordado", "Quantidade": str(len(df_matrizes))})
                            
                            st.dataframe(pd.DataFrame(extras_lista), use_container_width=True, hide_index=True)
                            
                            c_btn_est, c_btn_mat = st.columns(2)
                            with c_btn_est:
                                if not df_estampas.empty:
                                    if st.button("🔍 Estampa", key=f"btn_pop_est_{lote}", help="Ver itens de Estampa Extra", use_container_width=True):
                                        modal_detalhes_extra("Detalhamento de Estampa Extra", df_estampas, "valor_estampa_extra")
                            with c_btn_mat:
                                if not df_matrizes.empty:
                                    if st.button("🔍 Matriz Bordado", key=f"btn_pop_mat_{lote}", help="Ver itens de Matriz de Bordado", use_container_width=True):
                                        modal_detalhes_extra("Detalhamento de Matriz de Bordado", df_matrizes, "valor_matriz")

                    st.markdown(f"💰 **Valor Total Adiantado:** `R$ {total_pago:.2f}`")
                else:
                    st.caption("Nenhum item vinculado a este pedido.")

# -------------------------------------------------------------
# 5. TELA DASHBOARD INTERATIVO (EXCLUSIVO PARA ADMINISTRADORES)
# -------------------------------------------------------------
elif menu == "📈 Dashboard ADM" and is_admin:
    st.header("📈 Dashboard Analítico da Produção (Exclusivo ADM)")
    st.write("Acompanhe o desempenho, volume de produção por cor, produto e status em tempo real.")

    df_dash = carregar_dataframe("SELECT *, (preco + COALESCE(valor_estampa_extra, 0) + COALESCE(valor_matriz, 0)) as total_item FROM pedidos ORDER BY id DESC")

    if df_dash.empty:
        st.info("Nenhum pedido cadastrado no banco de dados para gerar indicadores.")
    else:
        df_dash["data_dt"] = pd.to_datetime(df_dash["data_criacao"], format="%d/%m/%Y", errors="coerce")
        
        st.markdown("### 🎯 Seleção do Escopo do Dashboard")
        col_dash_f1, col_dash_f2 = st.columns(2)
        with col_dash_f1:
            modo_filtro = st.radio("Filtrar Visão por:", ["Por Pedido Específico", "Por Período / Data"], horizontal=True)

        lotes_dash = ["Todos os Pedidos"] + list(df_dash["lote_id"].dropna().unique())

        if modo_filtro == "Por Pedido Específico":
            with col_dash_f2:
                ped_sel = st.selectbox("Selecione o Pedido:", lotes_dash)
            if ped_sel != "Todos os Pedidos":
                df_filtrado = df_dash[df_dash["lote_id"] == ped_sel]
            else:
                df_filtrado = df_dash.copy()
        else:
            data_min = df_dash["data_dt"].min() if not df_dash["data_dt"].dropna().empty else datetime.now()
            data_max = df_dash["data_dt"].max() if not df_dash["data_dt"].dropna().empty else datetime.now()
            with col_dash_f2:
                intervalo_datas = st.date_input("Selecione o Período:", value=(data_min, data_max))
                
            if isinstance(intervalo_datas, tuple) and len(intervalo_datas) == 2:
                d_ini, d_fim = intervalo_datas
                df_filtrado = df_dash[(df_dash["data_dt"] >= pd.to_datetime(d_ini)) & (df_dash["data_dt"] <= pd.to_datetime(d_fim))]
            else:
                df_filtrado = df_dash.copy()

        st.markdown("---")
        if df_filtrado.empty:
            st.warning("Nenhum registro encontrado para o filtro selecionado.")
        else:
            tot_bones = len(df_filtrado)
            val_total_prod = df_filtrado["total_item"].sum()
            ticket_medio = val_total_prod / tot_bones if tot_bones > 0 else 0
            entregues_cnt = len(df_filtrado[df_filtrado["status"] == "Entregue / Retirado"])
            pct_entregue = (entregues_cnt / tot_bones * 100) if tot_bones > 0 else 0

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total de Bonés", f"{tot_bones} un")
            kpi2.metric("Valor Total da Produção", f"R$ {val_total_prod:.2f}")
            kpi3.metric("Preço Médio / Boné", f"R$ {ticket_medio:.2f}")
            kpi4.metric("Concluídos / Entregues", f"{pct_entregue:.0f}%")

            st.markdown("---")
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.subheader("🎨 Distribuição por Cor do Boné")
                df_cores = df_filtrado.groupby("cor_bone").size().reset_index(name="Quantidade").sort_values(by="Quantidade", ascending=False)
                fig_cores = px.pie(df_cores, names="cor_bone", values="Quantidade", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_cores.update_traces(textinfo="value+percent")
                st.plotly_chart(fig_cores, use_container_width=True)

            with col_g2:
                st.subheader("📊 Status do Processo de Produção")
                df_status = df_filtrado.groupby("status").size().reset_index(name="Quantidade")
                ordem_st = {st_nome: i for i, st_nome in enumerate(STATUS_OPCOES)}
                df_status["ordem"] = df_status["status"].map(ordem_st)
                df_status = df_status.sort_values(by="ordem")
                fig_status = px.bar(
                    df_status, x="Quantidade", y="status", orientation="h", text="Quantidade", color="status",
                    color_discrete_map={"Em Produção": "#FFA500", "Concluído": "#2E8B57", "Entregue / Retirado": "#1E90FF"}
                )
                fig_status.update_traces(textposition="outside")
                fig_status.update_layout(showlegend=False, yaxis_title="")
                st.plotly_chart(fig_status, use_container_width=True)

            col_g3, col_g4 = st.columns(2)

            with col_g3:
                st.subheader("🧢 Produção por Modelo / Produto")
                df_tipo = df_filtrado.groupby("tipo").size().reset_index(name="Quantidade")
                fig_tipo = px.bar(df_tipo, x="tipo", y="Quantidade", text="Quantidade", color="tipo", color_discrete_sequence=px.colors.qualitative.Set2)
                fig_tipo.update_traces(textposition="outside")
                fig_tipo.update_layout(showlegend=False, xaxis_title="Modelo")
                st.plotly_chart(fig_tipo, use_container_width=True)

            with col_g4:
                st.subheader("🧵 Top 5 Cores de Estampa Mais Pedidas")
                df_linha = df_filtrado.groupby("cor_linha").size().reset_index(name="Quantidade").sort_values(by="Quantidade", ascending=False).head(5)
                fig_linha = px.bar(df_linha, x="Quantidade", y="cor_linha", orientation="h", text="Quantidade", color_discrete_sequence=["#8A2BE2"])
                fig_linha.update_traces(textposition="outside")
                fig_linha.update_layout(showlegend=False, yaxis_title="Cor da Linha")
                st.plotly_chart(fig_linha, use_container_width=True)

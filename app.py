import streamlit as st
import pandas as pd
import sqlite3
import os
from PIL import Image
from datetime import datetime

# Configuração da Página
st.set_page_config(
    page_title="R² BONÉS - Controle de Pedidos",
    page_icon="🧢",
    layout="wide"
)

# Estilo CSS customizado
st.markdown('''
<style>
    /* Estilo limpo para o status atual sem fundo colorido (Imagem 3) */
    .status-texto {
        font-weight: bold;
        color: #333333;
    }
    /* Estilo para tabela no resumo sem quebra de texto (Imagem 1) */
    .stDataFrame {
        white-space: nowrap;
    }
</style>
''', unsafe_allow_html=True)

# Banco de dados e diretório de uploads
DB_NAME = "ordens_producao.db"
UPLOADS_DIR = "uploads"

if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

def init_db():
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
            status TEXT
        )
    ''')
    
    # Migração para atualizar antigos 'Pendente' para 'Em Produção'
    c.execute("UPDATE pedidos SET status = 'Em Produção' WHERE status = 'Pendente'")
        
    conn.commit()
    conn.close()

def deletar_item(item_id):
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

init_db()

# Título Principal
st.title("🧢 R² BONÉS - Controle de Pedidos")

# -------------------------------------------------------------
# CONTROLE DE ACESSO / PERFIL
# -------------------------------------------------------------
st.sidebar.header("👤 Perfil de Acesso")
perfil = st.sidebar.selectbox("Acessar como:", ["Ateliê", "Administrador (Renan/Ronald)"])

is_admin = perfil == "Administrador (Renan/Ronald)"

# Definição do menu conforme o perfil
if is_admin:
    menu_options = ["➕ Encomenda", "📋 Produção", "📊 Tabela Geral"]
else:
    menu_options = ["📋 Produção", "📊 Tabela Geral"]

menu = st.sidebar.radio("Navegação", menu_options)

# -------------------------------------------------------------
# 1. TELA DE ENCOMENDA (ADMINISTRADOR)
# -------------------------------------------------------------
if menu == "➕ Encomenda":
    st.header("Cadastrar Item na Encomenda")
    st.write("Selecione um lote/pedido existente ou crie um novo para vincular os bonés.")

    # Buscar lotes já existentes no banco
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT DISTINCT lote_id FROM pedidos WHERE lote_id IS NOT NULL AND lote_id != '' ORDER BY id DESC")
    lotes_existentes = [row[0] for row in c.fetchall()]
    conn.close()

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        # Textos atualizados conforme solicitações
        opcao_lote = st.radio("Pedido:", ["Consulta Pedido", "Novo Pedido"], horizontal=True)
        
        if opcao_lote == "Consulta Pedido" and lotes_existentes:
            nome_lote = st.selectbox("Consultar Pedido", lotes_existentes)
        else:
            nome_lote_padrao = datetime.now().strftime("%d/%m/%Y")
            nome_lote = st.text_input("Nome do Novo Pedido:", value=nome_lote_padrao, help="Ex: 01/10/2026, Pedido Feirarte")

    with col_l2:
        st.info(f"📍 **Pedido Selecionado:** `{nome_lote}`")

    st.markdown("---")
    st.subheader("Detalhes do Boné Individual")

    with st.form("form_item_lote", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        # COLUNA DA ESQUERDA (Imagem 6)
        with col1:
            cor_bone = st.text_input("Cor do Boné", placeholder="Ex: Off White, Caramelo, Rosa Claro, Cinza")
            frase_arte = st.text_area("Arte Estampada", placeholder="Ex: Cariocando (com onda centralizada embaixo)")
            cor_linha = st.text_input("Cor da Estampa", placeholder="Ex: Azul, Preto, Off White, Bordô")
            # Imagem/Foto movida para a coluna da esquerda abaixo da Cor da Estampa
            uploaded_file = st.file_uploader("Foto / Imagem de Referência da Estampa (Opcional)", type=["jpg", "jpeg", "png", "webp"])

        # COLUNA DA DIREITA (Imagem 6)
        with col2:
            tipo = st.selectbox("Produto", ["Simples", "Premium", "Kids", "Outro"])
            # Preço sem botões - + (input livre editável)
            preco_str = st.text_input("Preço Unitário (R$)", value="29,00")
            observacoes = st.text_input("Observações Específicas", placeholder="Ex: Bordado frontal 12cm, fonte manuscrita")
            
            # Botão Adicionar posicionado do lado direito
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("➕ Adicionar Boné à Encomenda", use_container_width=True)

        if submit:
            try:
                preco_val = float(preco_str.replace(",", ".").replace("R$", "").strip())
            except ValueError:
                preco_val = 29.0

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

                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO pedidos (lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, observacoes, imagem_path, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (nome_lote, data_atual, cor_bone, frase_arte, cor_linha, tipo, preco_val, observacoes, img_path, "Em Produção"))
                conn.commit()
                conn.close()
                st.success(f"✅ Boné '{frase_arte}' adicionado com sucesso ao pedido '{nome_lote}'!")

    # Resumo da produção em tabela formatada (Imagem 1)
    st.markdown("---")
    st.subheader(f"📦 Resumo da Produção Pedido '{nome_lote}'")
    conn = sqlite3.connect(DB_NAME)
    df_lote_atual = pd.read_sql_query("SELECT id, cor_bone, frase_arte, cor_linha, tipo, preco, status, observacoes FROM pedidos WHERE lote_id = ? ORDER BY id DESC", conn, params=(nome_lote,))
    conn.close()

    if not df_lote_atual.empty:
        df_lote_atual["Preço"] = df_lote_atual["preco"].apply(lambda x: f"R$ {x:.2f}")
        df_lote_atual["Cor da Estampa"] = df_lote_atual["cor_linha"].apply(lambda x: x if x else "-")
        df_lote_atual["Observações"] = df_lote_atual["observacoes"].apply(lambda x: x if x else "-")
        
        df_display = df_lote_atual.rename(columns={
            "cor_bone": "Cor do Boné",
            "frase_arte": "Arte Estampada",
            "tipo": "Produto",
            "status": "Status"
        })[["Cor do Boné", "Arte Estampada", "Cor da Estampa", "Produto", "Preço", "Status", "Observações"]]

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        if is_admin:
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

        st.markdown("---")
        st.write(f"**Total de itens neste pedido:** {len(df_lote_atual)} boné(s) | **Valor Total:** R$ {df_lote_atual['preco'].sum():.2f}")
    else:
        st.caption("Nenhum boné cadastrado neste pedido ainda.")

# -------------------------------------------------------------
# 2. TELA DE PRODUÇÃO (Imagem 5)
# -------------------------------------------------------------
elif menu == "📋 Produção":
    st.header("📋 Produção")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM pedidos ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("Nenhum pedido cadastrado até o momento.")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.multiselect("Filtrar por Status", options=["Em Produção", "Concluído"], default=["Em Produção"])
        with col_f2:
            lotes_disponiveis = ["Todos"] + list(df["lote_id"].dropna().unique())
            lote_filter = st.selectbox("Filtrar por Lote / Encomenda", lotes_disponiveis)

        if status_filter:
            df = df[df["status"].isin(status_filter)]
        if lote_filter != "Todos":
            df = df[df["lote_id"] == lote_filter]

        st.caption(f"Exibindo {len(df)} boné(s)")

        for idx, row in df.iterrows():
            with st.container():
                st.markdown("---")
                col_img, col_info, col_status = st.columns([1.2, 2, 1])
                with col_img:
                    if row["imagem_path"] and os.path.exists(row["imagem_path"]):
                        st.image(row["imagem_path"], use_container_width=True, caption="Foto de Referência")
                    else:
                        st.warning("⚠️ Sem foto de referência cadastrada")
                with col_info:
                    st.subheader(f"Boné: {row['cor_bone']}")
                    if row["lote_id"]:
                        st.markdown(f"📦 **Pedido:** `{row['lote_id']}`")
                    
                    # Estilo idêntico com caixa de código para Arte e Cor da Estampa (Imagem 4)
                    arte_fmt = f"`{row['frase_arte']}`" if row['frase_arte'] else "-"
                    cor_linha_fmt = f"`{row['cor_linha']}`" if row['cor_linha'] else "-"
                    
                    st.markdown(f"**Arte Estampada:** {arte_fmt}")
                    st.markdown(f"**Cor da Estampa:** {cor_linha_fmt}")
                    st.markdown(f"**Produto:** `{row['tipo']}`")
                    if row["observacoes"]:
                        st.info(f"📌 **Obs:** {row['observacoes']}")
                with col_status:
                    # Data sem a hora (Imagem 4)
                    data_so_data = row['data_criacao'].split(" ")[0] if row['data_criacao'] else ""
                    st.write(f"**Data:** {data_so_data}")
                    
                    # Sem preenchimento de fundo colorido no texto do status (Imagem 3)
                    st.markdown(f"**Status Atual:** **{row['status']}**")
                    
                    novo_status = st.selectbox(
                        "Atualizar Status", 
                        ["Em Produção", "Concluído"], 
                        index=["Em Produção", "Concluído"].index(row["status"]) if row["status"] in ["Em Produção", "Concluído"] else 0, 
                        key=f"status_{row['id']}"
                    )
                    if novo_status != row["status"]:
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE pedidos SET status = ? WHERE id = ?", (novo_status, row['id']))
                        conn.commit()
                        conn.close()
                        st.rerun()

                    if is_admin:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🗑️️ Excluir Item", key=f"btn_del_card_{row['id']}", type="secondary"):
                            deletar_item(row['id'])
                            st.success("Item excluído!")
                            st.rerun()

# -------------------------------------------------------------
# 3. TABELA GERAL
# -------------------------------------------------------------
elif menu == "📊 Tabela Geral":
    st.header("📊 Tabela Geral de Pedidos")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT id, lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, status, observacoes FROM pedidos ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("Nenhum pedido cadastrado.")
    else:
        df['lote_id'] = df['lote_id'].fillna('Sem Lote Definido')
        lotes_unicos = df['lote_id'].unique()

        for lote in lotes_unicos:
            df_lote = df[df['lote_id'] == lote].copy()
            total_qtd = len(df_lote)
            total_valor = df_lote['preco'].sum()
            
            with st.expander(f"📦 Pedido: {lote} — ({total_qtd} bonés | Total: R$ {total_valor:.2f})", expanded=False):
                df_lote["preco"] = df_lote["preco"].apply(lambda x: f"R$ {x:.2f}")
                df_lote["data_criacao"] = df_lote["data_criacao"].apply(lambda x: x.split(" ")[0] if x else "")
                
                cols_ordem = ["cor_bone", "frase_arte", "cor_linha", "tipo", "preco", "status", "observacoes", "data_criacao"]
                df_exibicao_lote = df_lote[cols_ordem].rename(columns={
                    "cor_bone": "Cor do Boné",
                    "frase_arte": "Arte Estampada",
                    "cor_linha": "Cor da Estampa",
                    "tipo": "Produto",
                    "preco": "Preço",
                    "status": "Status",
                    "observacoes": "Observações",
                    "data_criacao": "Data"
                })
                
                if is_admin:
                    col_t, col_d = st.columns([4, 1])
                    with col_t:
                        st.dataframe(df_exibicao_lote, use_container_width=True, hide_index=True)
                    with col_d:
                        st.markdown("##### 🗑️ Excluir Item")
                        dict_itens_tbl = {row["id"]: f"{row['cor_bone']} - {row['frase_arte']}" for _, row in df_lote.iterrows()}
                        id_del = st.selectbox("Item:", options=list(dict_itens_tbl.keys()), format_func=lambda x: dict_itens_tbl[x], key=f"sel_tbl_{lote}")
                        if st.button("❌ Excluir", key=f"btn_del_tbl_{lote}"):
                            deletar_item(id_del)
                            st.success("Item excluído!")
                            st.rerun()
                else:
                    st.dataframe(df_exibicao_lote, use_container_width=True, hide_index=True)
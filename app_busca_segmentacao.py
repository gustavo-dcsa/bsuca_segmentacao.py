import streamlit as st
import pandas as pd
import json
import os
import re
import time
import asyncio
from unidecode import unidecode
from dotenv import load_dotenv
from datetime import datetime

# Agno Imports
from src.database import initialize_knowledge_base
from src.agent import get_auditor_agent, ResultadoAuditoria

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
st.set_page_config(page_title="Segmentação Médica IA (Agno)", layout="wide", page_icon="🩺")

# Ensure GOOGLE_API_KEY is set for Agno/Gemini
if os.getenv("API_PROJETOS_UNI_GMINAI"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("API_PROJETOS_UNI_GMINAI")

# Configurações Globais
DIR_BASES = "bases"
FILE_PATH_MAIN = os.path.join(DIR_BASES, "classificacao_procedimentos.csv")
FILE_PATH_ERRORS = os.path.join(DIR_BASES, "inconsistencias.csv")
API_KEY = os.getenv("API_PROJETOS_UNI_GMINAI")
MAX_CONCURRENT_REQUESTS = 5

# Colunas Oficiais
COLS_FULL = [
    "CODIGO", "DESCRICAO", "ABREVIATURA", "ITEM", "SEGMENTACAO",
    "TERAPIA_ESPECIAL", "TIPO_MEDICAMENTO", "TIPO_CANCER",
    "CODIGO_SUGERIDO", "DESCRICAO_SUGERIDA", "NIVEL_CONFIANCA",
    "JUSTIFICATIVA", "DATA_MODIFICACAO"
]

# Verifica e cria diretório de bases se não existir
if not os.path.exists(DIR_BASES):
    os.makedirs(DIR_BASES)

if not API_KEY:
    st.error("⚠️ API Key não encontrada no arquivo .env (API_PROJETOS_UNI_GMINAI)")
    st.stop()

# --- FUNÇÕES UTILITÁRIAS ---

def normalizar_texto(texto):
    """Remove acentos, espaços extras e converte para maiúsculo."""
    if not isinstance(texto, str):
        return ""
    return unidecode(texto).strip().upper()

def carregar_dados():
    """Carrega as bases de dados ou cria vazias se não existirem (Para UI e edição)."""
    if "main_df" not in st.session_state:
        if os.path.exists(FILE_PATH_MAIN):
            st.session_state.main_df = pd.read_csv(FILE_PATH_MAIN, sep=";", dtype=str, encoding='latin1')
        else:
            st.session_state.main_df = pd.DataFrame(columns=COLS_FULL)

    if "inconsistencias_df" not in st.session_state:
        if os.path.exists(FILE_PATH_ERRORS):
            st.session_state.inconsistencias_df = pd.read_csv(FILE_PATH_ERRORS, sep=";", dtype=str, encoding='latin1')
        else:
            st.session_state.inconsistencias_df = pd.DataFrame(columns=COLS_FULL)

def salvar_dados():
    """Persiste os dataframes em CSV."""
    st.session_state.main_df.to_csv(FILE_PATH_MAIN, sep=";", index=False, encoding='latin1')
    st.session_state.inconsistencias_df.to_csv(FILE_PATH_ERRORS, sep=";", index=False, encoding='latin1')

# --- AGNO INTEGRATION ---

@st.cache_resource
def get_cached_knowledge_base():
    """Initializes Knowledge Base (Cached)."""
    return initialize_knowledge_base()

def initialize_agent():
    """Initializes the Agent in Session State."""
    if "auditor_agent" not in st.session_state:
        with st.spinner("Inicializando Agente e Base de Conhecimento..."):
            kb = get_cached_knowledge_base()
            st.session_state.auditor_agent = get_auditor_agent(knowledge_base=kb)

def exibir_resultado_agno(resultado: ResultadoAuditoria):
    """Exibe resultado estruturado vindo do objeto Pydantic do Agno."""
    st.markdown("### Resultado Encontrado (Agente)")
    # Seção Principal: 3 Colunas Grandes
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Descrição")
        st.write(resultado.descricao_procedimento)
    with col2:
        st.subheader("Código")
        st.write(resultado.codigo_sugerido)
    with col3:
        conf = resultado.nivel_confianca
        cor_conf = "green" if conf == "ALTO" else "orange" if conf == "MEDIO" else "red"
        st.subheader("Nível de Confiança")
        st.markdown(f":{cor_conf}[**{conf}**]")
    # Seção Detalhes Específicos
    st.markdown("---")
    col_det1, col_det2 = st.columns(2)
    with col_det1:
        if resultado.item:
            st.write(f"**Item:** {resultado.item}")
        st.write(f"**Segmentação:** {resultado.segmentacao or ''}")
    with col_det2:
        if resultado.segmentacao == "SAT":
            st.write(f"**Terapia Especial:** {resultado.terapia_especial or ''}")
        elif resultado.item == "MEDICAMENTOS":
            st.write(f"**Tipo Medicamento:** {resultado.tipo_medicamento or ''}")
            st.write(f"**Tipo Câncer:** {resultado.tipo_cancer or ''}")
    # Justificativa em texto menor
    st.markdown("---")
    st.caption(f"📝 **Justificativa:** {resultado.justificativa_tecnica}")

def result_to_dict(resultado: ResultadoAuditoria, input_cod="", input_desc=""):
    """Converte objeto Pydantic para dicionário compatível com DataFrame."""
    return {
        "CODIGO": input_cod,
        "DESCRICAO": input_desc,
        "ABREVIATURA": resultado.abreviatura or "",
        "ITEM": resultado.item or "",
        "SEGMENTACAO": resultado.segmentacao or "",
        "TERAPIA_ESPECIAL": resultado.terapia_especial or "NÃO",
        "TIPO_MEDICAMENTO": resultado.tipo_medicamento or "",
        "TIPO_CANCER": resultado.tipo_cancer or "",
        "CODIGO_SUGERIDO": resultado.codigo_sugerido,
        "DESCRICAO_SUGERIDA": resultado.descricao_procedimento,
        "NIVEL_CONFIANCA": resultado.nivel_confianca,
        "JUSTIFICATIVA": resultado.justificativa_tecnica,
        "DATA_MODIFICACAO": datetime.now().strftime("%d/%m/%Y")
    }

# --- PROCESSAMENTO EM LOTE (COM AGNO) ---

async def processar_linha_agno(agent, row, semaphore):
    async with semaphore:
        cod = str(row.get("CODIGO", "")).replace("nan", "")
        desc = str(row.get("DESCRICAO_BUSCA", ""))

        query = f"Código: {cod}, Descrição: {desc}" if cod else f"Descrição: {desc}"

        try:
            # We use add_history_to_context=False to treat each row independently
            # and avoid polluting context or hitting token limits.
            response = await asyncio.to_thread(agent.run, query, add_history_to_context=False)
            resultado: ResultadoAuditoria = response.content
            return result_to_dict(resultado, cod, desc)
        except Exception as e:
            # Fallback erro
            return {
                "CODIGO": cod, "DESCRICAO": desc,
                "NIVEL_CONFIANCA": "ERRO",
                "JUSTIFICATIVA": f"Erro Agente: {str(e)}",
                 "DATA_MODIFICACAO": datetime.now().strftime("%d/%m/%Y")
            }

async def processar_lote_agno_async(df_batch):
    agent = st.session_state.auditor_agent
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    tasks = []
    for idx, row in df_batch.iterrows():
        tasks.append(processar_linha_agno(agent, row, semaphore))

    return await asyncio.gather(*tasks)

# --- REIMPLEMENTAÇÃO AUTO-CLASSIFICAÇÃO (Agno) ---

def classificar_dados_agno():
    """
    Classifica campos em branco/nulos da base usando IA (Agno Agent).
    Versão simplificada e síncrona (loop com barra de progresso na UI).
    """
    if 'main_df' not in st.session_state or st.session_state.main_df.empty:
        return

    df = st.session_state.main_df

    # 1. Identificar linhas (mesma lógica original)
    mask_item_vazio = (df['ITEM'].isna()) | (df['ITEM'] == '')
    indices_item = df[mask_item_vazio & (df['DESCRICAO'] != '')].index.tolist()

    mask_item_servico_med = df['ITEM'].isin(['SERVIÇO', 'MEDICAMENTOS'])
    mask_segmentacao_vazio = (df['SEGMENTACAO'].isna()) | (df['SEGMENTACAO'] == '')
    indices_segmentacao = df[mask_item_servico_med & mask_segmentacao_vazio & (df['DESCRICAO'] != '')].index.tolist()

    mask_sat = df['SEGMENTACAO'] == 'SAT'
    mask_terapia_vazio = (df['TERAPIA_ESPECIAL'].isna()) | (df['TERAPIA_ESPECIAL'] == '')
    indices_terapia = df[mask_sat & mask_terapia_vazio & (df['DESCRICAO'] != '')].index.tolist()

    mask_abreviatura_vazio = (df['ABREVIATURA'].isna()) | (df['ABREVIATURA'] == '')
    indices_abreviatura = df[mask_sat & mask_abreviatura_vazio & (df['DESCRICAO'] != '')].index.tolist()

    mask_medicamento = df['ITEM'] == 'MEDICAMENTOS'
    mask_tipo_med_vazio = (df['TIPO_MEDICAMENTO'].isna()) | (df['TIPO_MEDICAMENTO'] == '')
    mask_tipo_cancer_vazio = (df['TIPO_CANCER'].isna()) | (df['TIPO_CANCER'] == '')
    indices_medicamento = df[mask_medicamento & (mask_tipo_med_vazio | mask_tipo_cancer_vazio) & (df['DESCRICAO'] != '')].index.tolist()

    indices_processar = sorted(set(indices_item + indices_segmentacao + indices_terapia + indices_medicamento + indices_abreviatura))

    if not indices_processar:
        return

    st.info(f"Iniciando enriquecimento da base (Agno). Total: {len(indices_processar)}")
    barra_progresso = st.progress(0)
    status_text = st.empty()

    agent = st.session_state.auditor_agent
    total_items = len(indices_processar)

    for i, idx in enumerate(indices_processar):
        progresso = (i + 1) / total_items
        barra_progresso.progress(progresso)

        row = df.loc[idx]
        cod = str(row.get('CODIGO', '')).strip()
        desc = str(row.get('DESCRICAO', '')).strip()

        status_text.markdown(f"Running... {i+1}/{total_items}: `{cod}` - *{desc}*")

        if not desc: continue

        query = f"Código: {cod}, Descrição: {desc}" if cod else f"Descrição: {desc}"

        try:
            # Synchronous run for startup process (simpler UI update)
            response = agent.run(query, add_history_to_context=False)
            resultado: ResultadoAuditoria = response.content
            res_dict = result_to_dict(resultado, cod, desc)

            # Update Logic
            linha_idx = idx # Assuming index aligns if we didn't filter copy.
            # Wait, df is reference to st.session_state.main_df?
            # Yes: df = st.session_state.main_df

            # Update specific fields
            for col in COLS_FULL:
                if col not in ['DESCRICAO_SUGERIDA', 'NIVEL_CONFIANCA', 'JUSTIFICATIVA', 'DATA_MODIFICACAO']:
                    valor_atual = st.session_state.main_df.at[linha_idx, col]
                    if pd.isna(valor_atual) or valor_atual == '':
                         # Map from res_dict to DataFrame column
                         if res_dict.get(col):
                             st.session_state.main_df.at[linha_idx, col] = res_dict[col]

            st.session_state.main_df.at[linha_idx, 'DESCRICAO_SUGERIDA'] = res_dict['DESCRICAO_SUGERIDA']
            st.session_state.main_df.at[linha_idx, 'NIVEL_CONFIANCA'] = res_dict['NIVEL_CONFIANCA']
            st.session_state.main_df.at[linha_idx, 'JUSTIFICATIVA'] = res_dict['JUSTIFICATIVA']
            st.session_state.main_df.at[linha_idx, 'DATA_MODIFICACAO'] = res_dict['DATA_MODIFICACAO']

            # Move low confidence
            if res_dict['NIVEL_CONFIANCA'] != "ALTO":
                 linha_para_mover = st.session_state.main_df.loc[linha_idx].to_dict()
                 st.session_state.main_df.drop(linha_idx, inplace=True)
                 st.session_state.inconsistencias_df = pd.concat(
                    [st.session_state.inconsistencias_df, pd.DataFrame([linha_para_mover])],
                    ignore_index=True
                )

            salvar_dados()

        except Exception as e:
            # st.error(f"Erro item {idx}: {e}")
            continue

    status_text.text("Processo finalizado!")
    time.sleep(1)

# --- INICIALIZAÇÃO ---

# 1. Carregar DataFrame
carregar_dados()

# 2. Inicializar Agente
initialize_agent()

# 3. Auto-Classificação na Inicialização (Agno)
if "dados_classificados" not in st.session_state:
    loading_placeholder = st.empty()
    with loading_placeholder.container():
        st.header("🚀 Iniciando Aplicação")
        st.write("Aguarde enquanto enriquecemos a base de dados com Agno Agent...")
        with st.spinner('Processando...'):
             classificar_dados_agno()

    loading_placeholder.empty()
    st.session_state.dados_classificados = True
    st.rerun()

# BARRA LATERAL
st.sidebar.image("C:/Users/gustavo.santos/Documents/Imagens e Icones/Icones/hospital (1).png", width=60)
st.sidebar.title("Classificador Agno")
page = st.sidebar.radio("Navegação", ["🔍 Busca Individual", "🚀 Busca em Lote", "🛠️ Corrigir e Treinar"])

st.sidebar.markdown("---")
st.sidebar.header("📩 Downloads")
st.sidebar.download_button(
    "Baixar Base Oficial (.csv)",
    st.session_state.main_df.to_csv(sep=";", index=False, encoding='utf-8').encode("utf-8"),
    "classificacao_procedimentos.csv"
)

# PÁGINA 1: BUSCA INDIVIDUAL
if page == "🔍 Busca Individual":
    st.header("Busca e Classificação Individual (Powered by Agno)")

    c1, c2 = st.columns([1, 3])
    input_cod = c1.text_input("Código (Opcional)", placeholder="Ex: 50000160")
    input_desc = c2.text_input("Descrição do Procedimento", placeholder="Ex: SESSÃO DE PSICOMOTRICIDADE")

    if st.button("Pesquisar / Classificar", type="primary"):
        if not input_cod and not input_desc:
            st.warning("❗Por favor, insira pelo menos um campo.")
            st.stop()

        query = f"Código: {input_cod}, Descrição: {input_desc}" if input_cod else f"Descrição: {input_desc}"

        with st.spinner("Consultando Agente Especialista..."):
            try:
                agent = st.session_state.auditor_agent
                response = agent.run(query)
                resultado: ResultadoAuditoria = response.content

                exibir_resultado_agno(resultado)

                # Convert to dict for saving logic
                res_dict = result_to_dict(resultado, input_cod, input_desc)

                # Show tools usage if available
                if hasattr(response, 'tools') and response.tools:
                    with st.expander("Ver Raciocínio (Tools)"):
                        st.write(response.tools)

                # Persistência
                if resultado.nivel_confianca == "ALTO":
                    st.session_state.main_df = pd.concat([st.session_state.main_df, pd.DataFrame([res_dict])], ignore_index=True)
                    st.toast("Salvo na Base Oficial", icon="✅")
                else:
                    st.session_state.inconsistencias_df = pd.concat([st.session_state.inconsistencias_df, pd.DataFrame([res_dict])], ignore_index=True)
                    st.toast("Enviado para Inconsistências", icon="⚠️")

                salvar_dados()

            except Exception as e:
                st.error(f"Erro no Agente: {e}")

# PÁGINA 2: LOTE
elif page == "🚀 Busca em Lote":
    st.header("Processamento em Lote (Agno Agent)")
    st.markdown("Faça upload de um CSV contendo a coluna ```DESCRICAO_BUSCA```.")

    uploaded = st.file_uploader("Arquivo CSV", type=["csv"])

    if uploaded:
        df_up = pd.read_csv(uploaded, sep=";", dtype=str, encoding='utf-8')
        if "DESCRICAO_BUSCA" not in df_up.columns:
            df_up = pd.read_csv(uploaded, sep=",", dtype=str, encoding='utf-8')

        if "DESCRICAO_BUSCA" in df_up.columns:
            st.info(f"{len(df_up)} registros carregados.")

            if st.button("Iniciar Processamento"):
                progress_bar = st.progress(0, "Iniciando...")

                # Agno Agent might be rate limited if concurrent, but we try async wrapper
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                resultados = loop.run_until_complete(processar_lote_agno_async(df_up))

                progress_bar.progress(100, "Concluído!")

                novos_altos = [r for r in resultados if r.get("NIVEL_CONFIANCA") == "ALTO"]
                novos_baixos = [r for r in resultados if r.get("NIVEL_CONFIANCA") != "ALTO"]

                if novos_altos:
                    st.session_state.main_df = pd.concat([st.session_state.main_df, pd.DataFrame(novos_altos)], ignore_index=True)
                if novos_baixos:
                    st.session_state.inconsistencias_df = pd.concat([st.session_state.inconsistencias_df, pd.DataFrame(novos_baixos)], ignore_index=True)

                salvar_dados()

                c1, c2 = st.columns(2)
                c1.success(f"✅ {len(novos_altos)} salvos na Base Oficial")
                c2.warning(f"⚠️ {len(novos_baixos)} enviados para Inconsistências")

                df_resultado_lote = pd.DataFrame(resultados)
                st.download_button(
                    "📥 Baixar Resultado",
                    df_resultado_lote.to_csv(sep=";", index=False, encoding='utf-8').encode("utf-8"),
                    "resultado_lote.csv",
                    "text/csv"
                )

# PÁGINA 3: CORREÇÃO (MANTIDA IGUAL MAS SALVA NA BASE QUE SERÁ INPUT DO AGENTE)
elif page == "🛠️ Corrigir e Treinar":
    st.header("Correção de Inconsistências")

    if not st.session_state.inconsistencias_df.empty:
        df_edit = st.session_state.inconsistencias_df.copy()
        df_edit.insert(0, "STATUS", df_edit["NIVEL_CONFIANCA"].apply(lambda x: "🔴" if x == "BAIXO" else "🟡"))

        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            num_rows="fixed",
            key="editor_fix",
            column_config={
                "STATUS": st.column_config.TextColumn("Status", disabled=True, width="small"),
                "JUSTIFICATIVA": st.column_config.TextColumn("Justificativa IA", disabled=True)
            },
            hide_index=True,
        )

        if st.button("💾 Validar e Mover para Base Oficial"):
            if "STATUS" in edited_df.columns:
                edited_df = edited_df.drop(columns=["STATUS"])

            edited_df["NIVEL_CONFIANCA"] = "ALTO"
            edited_df["JUSTIFICATIVA"] = "Validado Manualmente"

            st.session_state.main_df = pd.concat([st.session_state.main_df, edited_df], ignore_index=True)
            st.session_state.inconsistencias_df = pd.DataFrame(columns=COLS_FULL)

            salvar_dados()
            st.success("Base atualizada! (Nota: Reinicie o app para re-treinar a Base de Conhecimento com novos dados)")
            st.rerun()
    else:
        st.success("🎉 Nenhuma inconsistência pendente!")

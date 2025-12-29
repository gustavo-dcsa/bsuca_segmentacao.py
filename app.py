import streamlit as st
from agno.agent import Agent
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb
import os
import pandas as pd
from dotenv import load_dotenv

# Import our custom modules
from src.knowledge import get_knowledge_base, initialize_knowledge_base
from src.models import ResultadoAuditoria
from src.agent import get_auditor_agent

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
st.set_page_config(page_title="Auditor Médico Agno", layout="wide", page_icon="🩺")

# --- INITIALIZATION FUNCTIONS ---

@st.cache_resource
def setup_knowledge():
    """
    Initializes the knowledge base only once.
    """
    try:
        kb = get_knowledge_base()
        # Initialize (load data) if not already done
        with st.spinner("Inicializando Base de Conhecimento (LanceDB)..."):
             initialize_knowledge_base(kb)
        return kb
    except Exception as e:
        st.error(f"Erro ao inicializar Knowledge Base: {e}")
        return None

def get_session_agent():
    """
    Gets or creates the agent in session state.
    """
    if "session_id" not in st.session_state:
        st.session_state.session_id = "sessao_padrao" # Could be dynamic per user

    if "auditor_agent" not in st.session_state:
        # Create agent with storage
        agent = get_auditor_agent(session_id=st.session_state.session_id)
        st.session_state.auditor_agent = agent

    return st.session_state.auditor_agent

# --- UI ---

st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3063/3063176.png", width=60) # Generic Icon
st.sidebar.title("Auditor Médico Agno")
st.sidebar.markdown("Arquitetura Agêntica com RAG")

page = st.sidebar.radio("Navegação", ["Auditoria Individual", "Sobre"])

if page == "Auditoria Individual":
    st.title("Auditor Médico via Agno & Gemini")

    # Ensure KB is loaded
    kb = setup_knowledge()
    if not kb:
        st.stop()

    # Get Agent
    agent = get_session_agent()

    # Input
    user_query = st.text_input("Descreva o procedimento, material ou código:", placeholder="Ex: Fio Ti-Cron ou 1008658")

    if st.button("Classificar Procedimento", type="primary") and user_query:
        with st.spinner("Consultando base de conhecimento e analisando..."):
            try:
                # Execução do Agente
                response = agent.run(user_query)

                # Acesso ao objeto Pydantic
                resultado: ResultadoAuditoria = response.content

                # Exibição
                st.markdown("### Resultado da Auditoria")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Código Sugerido", resultado.codigo_sugerido)
                with col2:
                    st.metric("Confiança", resultado.nivel_confianca)

                with col3:
                     st.write(f"**Segmentação:** {resultado.segmentacao}")
                     if resultado.item:
                         st.write(f"**Item:** {resultado.item}")

                st.info(f"**Descrição Oficial:** {resultado.descricao_procedimento}")
                st.success(f"**Justificativa Técnica:** {resultado.justificativa_tecnica}")

                with st.expander("Detalhes Adicionais"):
                    if resultado.terapia_especial:
                        st.write(f"**Terapia Especial:** {resultado.terapia_especial}")
                    if resultado.tipo_medicamento:
                        st.write(f"**Tipo Medicamento:** {resultado.tipo_medicamento}")
                    if resultado.tipo_cancer:
                        st.write(f"**Tipo Câncer:** {resultado.tipo_cancer}")

                with st.expander("Ver Raciocínio (Tools)"):
                    if hasattr(response, 'tools'):
                        st.write(response.tools)
                    else:
                        st.write("Nenhuma ferramenta foi chamada explicitamente ou log não disponível.")

            except Exception as e:
                st.error(f"Erro durante a execução do agente: {e}")
                # Optional: print traceback
                import traceback
                st.code(traceback.format_exc())

elif page == "Sobre":
    st.markdown("""
    ## Sobre o Projeto

    Esta aplicação utiliza o framework **Agno** para orquestrar agentes de IA.

    **Stack Tecnológico:**
    - **LLM:** Google Gemini 2.0 Flash
    - **Vector DB:** LanceDB (Local/Serverless)
    - **Framework:** Agno (Phidata)
    - **Frontend:** Streamlit

    A base de conhecimento é carregada de um arquivo CSV e indexada vetorialmente para busca híbrida (semântica + keyword).
    """)

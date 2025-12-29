from agno.agent import Agent
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb
import os

from src.models import ResultadoAuditoria
from src.knowledge import get_knowledge_base

def get_auditor_agent(session_id: str = None, storage_path: str = "tmp/app_data.db"):
    """
    Cria e configura o Agente Auditor.
    """

    knowledge_base = get_knowledge_base()

    db_instance = None
    if session_id:
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        db_instance = SqliteDb(
            table_name="agent_sessions",
            db_url=f"sqlite:///{storage_path}"
        )

    model_id = "gemini-2.0-flash"

    auditor_medico = Agent(
        name="Auditor Médico Agno",
        model=Gemini(
            id=model_id,
            max_output_tokens=8192,
            temperature=0.1
        ),

        # Integração da Base de Conhecimento
        knowledge=knowledge_base,
        search_knowledge=True,

        # Definição de Saída Estruturada
        output_schema=ResultadoAuditoria,

        # Instruções de Comportamento
        description="Você é um Auditor Médico Senior especializado em codificação de procedimentos hospitalares.",
        instructions=[
            "Você deve consultar a Base de Conhecimento para encontrar o código correto.",
            "Compare a descrição fornecida pelo usuário com as descrições na base.",
            "Se houver correspondência exata de código, use-a.",
            "Se a busca for por texto, procure o termo semanticamente mais próximo.",
            "Justifique sua escolha tecnicamente, explicando a relação entre o pedido e o código encontrado.",
            "Se não encontrar nada com confiança, marque como BAIXO nível de confiança.",
            "Preencha todos os campos do esquema de saída corretamente."
        ],

        # Persistence
        db=db_instance,
        session_id=session_id,
        add_history_to_context=True if session_id else False,

        # Debug - Removed show_tool_calls as it's not in __init__, likely used in .print_response() or handled via debug_mode
        debug_mode=True,
        markdown=True
    )

    return auditor_medico

from agno.agent import Agent
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb
from pydantic import BaseModel, Field
from typing import Optional

class ResultadoAuditoria(BaseModel):
    codigo_sugerido: str = Field(
       ...,
        description="O código numérico do procedimento encontrado na base de conhecimento. Deve conter 8 dígitos."
    )
    descricao_procedimento: str = Field(
       ...,
        description="A descrição oficial do procedimento conforme consta na base."
    )
    nivel_confianca: str = Field(
       ...,
        description="Nível de confiança da correspondência: 'ALTO', 'MEDIO' ou 'BAIXO'."
    )
    justificativa_tecnica: str = Field(
       ...,
        description="Explicação detalhada do porquê este código foi selecionado, comparando a entrada do usuário com a base."
    )
    segmentacao: Optional[str] = Field(
        None,
        description="A categoria do item (ex: MATERIAIS, SERVIÇO, MEDICAMENTOS)."
    )
    item: Optional[str] = Field(
        None,
        description="O tipo do item (ex: SERVIÇO, MEDICAMENTOS)."
    )
    terapia_especial: Optional[str] = Field(
        None,
        description="Informação sobre terapia especial, se aplicável."
    )
    tipo_medicamento: Optional[str] = Field(
        None,
        description="Tipo de medicamento, se aplicável."
    )
    tipo_cancer: Optional[str] = Field(
        None,
        description="Tipo de câncer, se aplicável."
    )
    abreviatura: Optional[str] = Field(
        None,
        description="Abreviatura do procedimento, se houver."
    )

def get_auditor_agent(knowledge_base, storage_path="tmp/agent_storage.db"):
    """
    Returns a configured Agno Agent for Medical Auditing.
    """

    # Storage for sessions (history)
    db = SqliteDb(
        table_name="auditor_sessions",
        db_url=f"sqlite:///{storage_path}"
    )

    agent = Agent(
        name="Auditor Médico",
        model=Gemini(
            id="gemini-2.0-flash",
            structured_outputs=True,
            temperature=0.1
        ),
        knowledge=knowledge_base,
        search_knowledge=True,
        # Persist session history using SqliteDb (passed to 'db' param)
        db=db,
        output_schema=ResultadoAuditoria,
        description="Você é um Auditor Médico Senior especializado em codificação de procedimentos hospitalares (TUSS/CBHPM/ANS).",
        instructions=[
            "Sua tarefa é classificar procedimentos médicos com base na descrição fornecida.",
            "Consulte SEMPRE a base de conhecimento para encontrar o código correspondente.",
            "Se a descrição for exata ou muito similar, retorne o código da base e confiança ALTO.",
            "Se houver dúvida ou ambiguidade, use confiança MEDIO ou BAIXO e justifique.",
            "O campo 'codigo_sugerido' deve ter exatamente 8 dígitos numéricos. Se não encontrar, deixe vazio ou indique erro na justificativa.",
            "Preencha todos os campos auxiliares (segmentacao, item, etc) conforme encontrado na base.",
        ],
        show_tool_calls=True,
        markdown=True,
        # We enable history accumulation by default for interactive sessions
        add_history_to_messages=True,
    )

    return agent

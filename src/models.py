from pydantic import BaseModel, Field
from typing import Optional

class ResultadoAuditoria(BaseModel):
    codigo_sugerido: str = Field(
       ...,
        description="O código numérico do procedimento encontrado na base de conhecimento."
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
        description="A categoria do item (ex: MATERIAIS, SERVIÇO, MEDICAMENTOS, SAT)."
    )
    item: Optional[str] = Field(
        None,
        description="O tipo do item (ex: MATERIAIS, SERVIÇO, MEDICAMENTOS, SAT)."
    )
    terapia_especial: Optional[str] = Field(
        None,
        description="Se segmentacao for SAT, qual a terapia (ex: PSICOMOTRICIDADE)."
    )
    tipo_medicamento: Optional[str] = Field(
        None,
        description="Se item for MEDICAMENTOS, qual o tipo."
    )
    tipo_cancer: Optional[str] = Field(
        None,
        description="Se item for MEDICAMENTOS, qual o tipo de câncer associado."
    )

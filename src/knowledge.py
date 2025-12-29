import os
from agno.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb, SearchType
from agno.knowledge.embedder.google import GeminiEmbedder
from agno.knowledge.reader.csv_reader import CSVReader

# Configuração do Caminho do Banco de Dados Vetorial Local
VECTOR_DB_PATH = "tmp/lancedb_medical_knowledge"
CSV_PATH = "data/classificacao_procedimentos.csv"

def get_knowledge_base():
    """
    Retorna a instância da Base de Conhecimento configurada.
    """

    # Check for API Key
    if not os.getenv("GOOGLE_API_KEY"):
         pass

    # Note: Knowledge in agno 2.x doesn't take 'reader' in init, it takes 'readers' dict or uses default.
    # However, we can pass a specific reader to 'add_content' (formerly load).

    knowledge_base = Knowledge(
        vector_db=LanceDb(
            table_name="medical_procedures",
            uri=VECTOR_DB_PATH,
            search_type=SearchType.hybrid,
            embedder=GeminiEmbedder(
                id="models/text-embedding-004",
                dimensions=768
            ),
        ),
        # We don't pass reader here anymore
    )
    return knowledge_base

def initialize_knowledge_base(knowledge_base: Knowledge):
    """
    Carrega o CSV para o banco vetorial se ainda não estiver populado.
    """
    if os.path.exists(CSV_PATH):
        # Create the specific CSV reader
        reader = CSVReader(
            delimiter=";",
            quotechar='"'
        )

        # Use add_content instead of load, passing the reader
        # skip_if_exists mimics recreate=False logic somewhat, or we rely on vector_db check
        # But to match 'recreate=False', we might want skip_if_exists=True
        knowledge_base.add_content(
            path=CSV_PATH,
            reader=reader,
            skip_if_exists=True
        )
    else:
        raise FileNotFoundError(f"Arquivo CSV não encontrado em: {CSV_PATH}")

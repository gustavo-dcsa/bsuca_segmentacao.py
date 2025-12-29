import os
from agno.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb, SearchType
from agno.knowledge.embedder.google import GeminiEmbedder
from agno.knowledge.reader.csv_reader import CSVReader

# Path to the vector database
VECTOR_DB_PATH = "tmp/lancedb_medical_knowledge"
CSV_PATH = "bases/classificacao_procedimentos.csv"

def initialize_knowledge_base():
    """
    Initializes and returns the Knowledge Base with LanceDB and Gemini Embeddings.
    Loads data if not already populated.
    """

    # Initialize the Knowledge Base
    knowledge_base = Knowledge(
        vector_db=LanceDb(
            table_name="medical_procedures",
            uri=VECTOR_DB_PATH,
            search_type=SearchType.hybrid,  # Hybrid search for better results
            embedder=GeminiEmbedder(
                id="models/text-embedding-004",
                dimensions=768
            ),
        ),
        reader=CSVReader(
            delimiter=";",  # Semicolon delimiter as per user spec
            quotechar='"'
        )
    )

    # Load data if the CSV exists and DB might need population
    # LanceDB is file-based, so we check if the path exists, but Knowledge.load(recreate=False) is safer
    if os.path.exists(CSV_PATH):
        try:
            # recreate=False ensures we don't duplicate data if it already exists
            knowledge_base.load(path=CSV_PATH, recreate=False)
            print(f"Knowledge Base loaded from {CSV_PATH}")
        except Exception as e:
            print(f"Error loading Knowledge Base: {e}")
    else:
        print(f"Warning: CSV file not found at {CSV_PATH}. Knowledge Base might be empty.")

    return knowledge_base

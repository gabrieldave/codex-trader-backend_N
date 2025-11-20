"""
🔍 EJEMPLO DE USO: BÚSQUEDA RAG CON FILTROS
===========================================

Ejemplo de cómo usar las funciones de búsqueda con filtros por metadatos
"""

from rag_search import search_with_filters, search_with_filters_llamaindex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.supabase import SupabaseVectorStore
import config

# ============================================================================
# EJEMPLO 1: Búsqueda simple con filtros
# ============================================================================

def ejemplo_busqueda_simple():
    """Búsqueda básica con filtros por metadatos"""
    
    query = "estrategias de trading"
    
    # Buscar solo en documentos en español de categoría "trading"
    resultados = search_with_filters(
        query=query,
        top_k=10,
        language="es",
        category="trading"
    )
    
    print(f"Encontrados {len(resultados)} resultados")
    for i, resultado in enumerate(resultados, 1):
        print(f"\n{i}. {resultado['document_info'].get('title', 'Sin título')}")
        print(f"   Autor: {resultado['document_info'].get('author', 'N/A')}")
        print(f"   Categoría: {resultado['document_info'].get('category', 'N/A')}")
        print(f"   Contenido: {resultado['content'][:200]}...")

# ============================================================================
# EJEMPLO 2: Búsqueda con múltiples filtros
# ============================================================================

def ejemplo_busqueda_multiple_filtros():
    """Búsqueda con varios filtros combinados"""
    
    query = "psicología positiva"
    
    resultados = search_with_filters(
        query=query,
        top_k=5,
        language="es",              # Solo español
        category="psicología",       # Solo psicología
        year_min=2020,               # Publicados después de 2020
        title_contains="positiva"    # Título debe contener "positiva"
    )
    
    print(f"Encontrados {len(resultados)} resultados")
    for resultado in resultados:
        doc_info = resultado['document_info']
        print(f"- {doc_info.get('title')} ({doc_info.get('published_year', 'N/A')})")

# ============================================================================
# EJEMPLO 3: Búsqueda por autor
# ============================================================================

def ejemplo_busqueda_por_autor():
    """Buscar documentos de un autor específico"""
    
    query = "inversiones"
    
    resultados = search_with_filters(
        query=query,
        top_k=10,
        author="Graham",  # Buscar por autor que contenga "Graham"
        language="es"
    )
    
    print(f"Encontrados {len(resultados)} resultados de autor 'Graham'")
    for resultado in resultados:
        print(f"- {resultado['document_info'].get('title')}")

# ============================================================================
# EJEMPLO 4: Búsqueda con LlamaIndex (recomendada)
# ============================================================================

def ejemplo_busqueda_llamaindex():
    """Búsqueda usando LlamaIndex (más precisa con embeddings)"""
    
    # Inicializar componentes
    embedding_model = OpenAIEmbedding(
        model="text-embedding-3-small",
        api_key=config.OPENAI_API_KEY
    )
    
    vector_store = SupabaseVectorStore(
        postgres_connection_string=config.postgres_connection_string,
        collection_name=config.VECTOR_COLLECTION_NAME
    )
    
    query = "cómo hacer trading"
    
    resultados = search_with_filters_llamaindex(
        query=query,
        vector_store=vector_store,
        embedding_model=embedding_model,
        top_k=10,
        language="es",
        category="trading",
        year_min=2020
    )
    
    print(f"Encontrados {len(resultados)} resultados")
    for resultado in resultados:
        print(f"- {resultado['document_info'].get('title')}")
        print(f"  Score: {resultado['score']:.4f}")

# ============================================================================
# EJEMPLO 5: Búsqueda sin filtros (todos los documentos)
# ============================================================================

def ejemplo_busqueda_sin_filtros():
    """Búsqueda sin filtros (busca en todos los documentos)"""
    
    query = "finanzas personales"
    
    resultados = search_with_filters(
        query=query,
        top_k=20
        # Sin filtros = busca en todos los documentos
    )
    
    print(f"Encontrados {len(resultados)} resultados en todos los documentos")

if __name__ == "__main__":
    print("="*80)
    print("EJEMPLOS DE BÚSQUEDA CON FILTROS")
    print("="*80)
    
    print("\n1. Búsqueda simple con filtros:")
    ejemplo_busqueda_simple()
    
    print("\n2. Búsqueda con múltiples filtros:")
    ejemplo_busqueda_multiple_filtros()
    
    print("\n3. Búsqueda por autor:")
    ejemplo_busqueda_por_autor()
    
    print("\n4. Búsqueda sin filtros:")
    ejemplo_busqueda_sin_filtros()


















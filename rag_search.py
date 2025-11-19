"""
🔍 BÚSQUEDA RAG CON FILTROS POR METADATOS
==========================================

Funciones para realizar búsquedas vectoriales con filtros por metadatos
de documentos (idioma, categoría, autor, año, etc.)
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def get_env(key):
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    raise ValueError("Faltan variables de entorno necesarias")

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

# Importar configuración
try:
    import config
    collection_name = config.VECTOR_COLLECTION_NAME
except ImportError:
    collection_name = "knowledge"  # Default

# ============================================================================
# FILTROS DE DOCUMENTOS
# ============================================================================

def get_filtered_doc_ids(
    language: Optional[str] = None,
    category: Optional[str] = None,
    author: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    title_contains: Optional[str] = None
) -> List[str]:
    """
    Obtiene los doc_ids de documentos que cumplen con los filtros especificados
    
    Args:
        language: Código de idioma (ej: 'es', 'en')
        category: Categoría/tema (ej: 'trading', 'psicología')
        author: Nombre del autor (búsqueda parcial, case-insensitive)
        year_min: Año mínimo de publicación
        year_max: Año máximo de publicación
        title_contains: Texto que debe contener el título (búsqueda parcial)
        
    Returns:
        Lista de doc_ids que cumplen los filtros
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor()
        
        # Construir query con filtros
        query = "SELECT doc_id FROM documents WHERE 1=1"
        params = []
        
        if language:
            query += " AND language = %s"
            params.append(language)
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        if author:
            query += " AND LOWER(author) LIKE %s"
            params.append(f"%{author.lower()}%")
        
        if year_min:
            query += " AND (published_year IS NULL OR published_year >= %s)"
            params.append(year_min)
        
        if year_max:
            query += " AND (published_year IS NULL OR published_year <= %s)"
            params.append(year_max)
        
        if title_contains:
            query += " AND LOWER(title) LIKE %s"
            params.append(f"%{title_contains.lower()}%")
        
        cur.execute(query, params)
        doc_ids = [row[0] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return doc_ids
        
    except Exception as e:
        print(f"⚠️  Error obteniendo doc_ids filtrados: {e}")
        return []

# ============================================================================
# BÚSQUEDA VECTORIAL CON FILTROS
# ============================================================================

def search_with_filters(
    query: str,
    top_k: int = 10,
    language: Optional[str] = None,
    category: Optional[str] = None,
    author: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    title_contains: Optional[str] = None,
    embedding_model: Optional[Any] = None,
    vector_store: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Realiza una búsqueda vectorial con filtros por metadatos
    
    Flujo:
    1. Filtrar documentos por metadatos (obtener doc_ids)
    2. Realizar búsqueda vectorial solo en chunks de esos doc_ids
    3. Devolver resultados con información de documentos
    
    Args:
        query: Texto de búsqueda
        top_k: Número de resultados a devolver
        language: Filtrar por idioma
        category: Filtrar por categoría
        author: Filtrar por autor
        year_min: Año mínimo
        year_max: Año máximo
        title_contains: Texto en título
        embedding_model: Modelo de embeddings (opcional, se usará para generar query embedding)
        vector_store: VectorStore de LlamaIndex (opcional)
        
    Returns:
        Lista de dicts con resultados:
        {
            'chunk_id': str,
            'doc_id': str,
            'content': str,
            'score': float,
            'metadata': dict,
            'document_info': dict  # Info de la tabla documents
        }
    """
    # Paso 1: Obtener doc_ids filtrados
    filtered_doc_ids = get_filtered_doc_ids(
        language=language,
        category=category,
        author=author,
        year_min=year_min,
        year_max=year_max,
        title_contains=title_contains
    )
    
    if not filtered_doc_ids:
        return []  # No hay documentos que cumplan los filtros
    
    # Paso 2: Realizar búsqueda vectorial en chunks filtrados
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Si tenemos embedding_model, generar embedding de la query
        # Si no, usar búsqueda por texto (menos preciso pero funcional)
        
        # Por ahora, búsqueda simple por texto en contenido
        # TODO: Integrar con LlamaIndex VectorStore para búsqueda vectorial real
        
        # Construir query SQL para buscar en chunks
        doc_ids_placeholders = ','.join(['%s'] * len(filtered_doc_ids))
        
        query_sql = f"""
            SELECT 
                id,
                metadata->>'chunk_id' as chunk_id,
                metadata->>'doc_id' as doc_id,
                metadata->>'file_name' as file_name,
                metadata->>'chunk_index' as chunk_index,
                metadata->>'content' as content,
                metadata->>'book_title' as book_title
            FROM vecs.{collection_name}
            WHERE metadata->>'doc_id' IN ({doc_ids_placeholders})
            AND (
                metadata->>'content' ILIKE %s
                OR metadata->>'book_title' ILIKE %s
            )
            LIMIT %s
        """
        
        params = filtered_doc_ids + [f"%{query}%", f"%{query}%", top_k]
        
        cur.execute(query_sql, params)
        results = cur.fetchall()
        
        # Paso 3: Obtener información de documentos
        doc_ids_in_results = list(set([r['doc_id'] for r in results if r['doc_id']]))
        
        documents_info = {}
        if doc_ids_in_results:
            doc_ids_placeholders = ','.join(['%s'] * len(doc_ids_in_results))
            cur.execute(f"""
                SELECT doc_id, filename, title, author, language, category, published_year
                FROM documents
                WHERE doc_id IN ({doc_ids_placeholders})
            """, doc_ids_in_results)
            
            for row in cur.fetchall():
                documents_info[row['doc_id']] = dict(row)
        
        cur.close()
        conn.close()
        
        # Formatear resultados
        formatted_results = []
        for result in results:
            doc_id = result['doc_id']
            formatted_results.append({
                'chunk_id': result.get('chunk_id'),
                'doc_id': doc_id,
                'content': result.get('content') or '',
                'score': 1.0,  # Placeholder, se calcularía con similitud vectorial
                'metadata': {
                    'file_name': result.get('file_name'),
                    'chunk_index': result.get('chunk_index'),
                    'book_title': result.get('book_title')
                },
                'document_info': documents_info.get(doc_id, {})
            })
        
        return formatted_results
        
    except Exception as e:
        print(f"⚠️  Error en búsqueda con filtros: {e}")
        return []

# ============================================================================
# FUNCIÓN DE BÚSQUEDA CON LLAMAINDEX (RECOMENDADA)
# ============================================================================

def search_with_filters_llamaindex(
    query: str,
    vector_store: Any,
    embedding_model: Any,
    top_k: int = 10,
    language: Optional[str] = None,
    category: Optional[str] = None,
    author: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    title_contains: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Realiza búsqueda vectorial usando LlamaIndex con filtros por metadatos
    
    Esta es la función recomendada para búsquedas reales con embeddings.
    
    Args:
        query: Texto de búsqueda
        vector_store: VectorStore de LlamaIndex (SupabaseVectorStore)
        embedding_model: Modelo de embeddings
        top_k: Número de resultados
        ... (resto de filtros igual que search_with_filters)
        
    Returns:
        Lista de resultados con información completa
    """
    # Paso 1: Obtener doc_ids filtrados
    filtered_doc_ids = get_filtered_doc_ids(
        language=language,
        category=category,
        author=author,
        year_min=year_min,
        year_max=year_max,
        title_contains=title_contains
    )
    
    if not filtered_doc_ids:
        return []
    
    # Paso 2: Crear query engine con filtros
    try:
        from llama_index.core import VectorStoreIndex, QueryBundle
        from llama_index.core.schema import NodeWithScore
        
        # Crear índice desde el vector store
        index = VectorStoreIndex.from_vector_store(vector_store)
        
        # Generar embedding de la query
        query_embedding = embedding_model.get_query_embedding(query)
        
        # Realizar búsqueda vectorial
        # Nota: Esto es un ejemplo simplificado
        # En producción, usarías el retriever de LlamaIndex con filtros de metadata
        
        # Por ahora, usar búsqueda directa en Supabase con filtros
        # TODO: Integrar completamente con LlamaIndex retriever
        
        return search_with_filters(
            query=query,
            top_k=top_k,
            language=language,
            category=category,
            author=author,
            year_min=year_min,
            year_max=year_max,
            title_contains=title_contains
        )
        
    except Exception as e:
        print(f"⚠️  Error en búsqueda LlamaIndex: {e}")
        return []
















"""
🏗️ INFRAESTRUCTURA RAG REUTILIZABLE
====================================

Paquete modular para sistemas RAG que incluye:
- Pipeline de ingesta optimizado
- Sistema anti-duplicados
- Extracción de metadatos ricos
- Logging profesional de errores
- Búsqueda con filtros
- Monitor y reportes

Uso básico:
    from rag_infrastructure import RAGIngestionPipeline
    
    pipeline = RAGIngestionPipeline(
        data_directory="./data",
        supabase_url="...",
        supabase_password="...",
        openai_api_key="..."
    )
    
    pipeline.ingest()
"""

__version__ = "1.0.0"

from .pipeline import RAGIngestionPipeline
from .metadata_extractor import extract_rich_metadata
from .error_logger import log_error, ErrorType, get_error_summary
from .rag_search import search_with_filters
from .anti_duplicates import calculate_doc_id, check_document_exists

__all__ = [
    'RAGIngestionPipeline',
    'extract_rich_metadata',
    'log_error',
    'ErrorType',
    'get_error_summary',
    'search_with_filters',
    'calculate_doc_id',
    'check_document_exists',
]




















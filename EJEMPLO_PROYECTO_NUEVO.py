"""
📚 EJEMPLO: USAR LA INFRAESTRUCTURA RAG EN UN NUEVO PROYECTO
============================================================

Este ejemplo muestra cómo usar la infraestructura RAG en un proyecto completamente nuevo.
"""

import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ============================================================================
# OPCIÓN 1: USO SIMPLE (Recomendado para empezar)
# ============================================================================

def ejemplo_uso_simple():
    """Uso más simple del pipeline completo"""
    
    from rag_infrastructure import RAGIngestionPipeline
    
    # Crear pipeline con configuración básica
    pipeline = RAGIngestionPipeline(
        data_directory="./mi_documentos",  # Tus documentos aquí
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_password=os.getenv("SUPABASE_DB_PASSWORD"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        collection_name="mi_coleccion"  # Nombre único para tu proyecto
    )
    
    # Ejecutar ingesta
    print("🚀 Iniciando ingesta...")
    results = pipeline.ingest()
    
    if results['success']:
        print("✅ Ingesta completada exitosamente!")
        print(f"   Archivos procesados: {results['results']['files_processed']}")
        print(f"   Chunks generados: {results['results']['chunks_generated']}")
    else:
        print(f"❌ Error: {results['error']}")
    
    # Realizar búsqueda
    print("\n🔍 Realizando búsqueda...")
    resultados = pipeline.search(
        query="¿Qué es machine learning?",
        language="es",
        top_k=5
    )
    
    print(f"\nEncontrados {len(resultados)} resultados:")
    for i, resultado in enumerate(resultados, 1):
        print(f"\n{i}. {resultado['document_info'].get('title', 'Sin título')}")
        print(f"   Autor: {resultado['document_info'].get('author', 'N/A')}")
        print(f"   Contenido: {resultado['content'][:150]}...")

# ============================================================================
# OPCIÓN 2: USO MODULAR (Para más control)
# ============================================================================

def ejemplo_uso_modular():
    """Uso modular de componentes individuales"""
    
    from rag_infrastructure.metadata_extractor import extract_rich_metadata
    from rag_infrastructure.anti_duplicates import calculate_doc_id, register_document
    from rag_infrastructure.error_logger import log_error, ErrorType
    from rag_infrastructure.rag_search import search_with_filters
    
    # 1. Extraer metadatos de un documento
    file_path = "./documento.pdf"
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    metadata = extract_rich_metadata(file_path, text=text)
    print(f"Título: {metadata['title']}")
    print(f"Autor: {metadata['author']}")
    print(f"Idioma: {metadata['language']}")
    print(f"Categoría: {metadata['category']}")
    
    # 2. Calcular ID único y registrar
    doc_id = calculate_doc_id(file_path)
    register_document(
        doc_id=doc_id,
        filename=os.path.basename(file_path),
        file_path=file_path,
        title=metadata['title'],
        author=metadata['author'],
        language=metadata['language'],
        category=metadata['category']
    )
    
    # 3. Realizar búsqueda
    resultados = search_with_filters(
        query="machine learning",
        top_k=10,
        language="es"
    )
    
    # 4. Manejar errores
    try:
        # Tu código aquí
        pass
    except Exception as e:
        log_error(
            filename="documento.pdf",
            error_type=ErrorType.UNKNOWN_ERROR,
            error_message=str(e),
            exception=e
        )

# ============================================================================
# OPCIÓN 3: INTEGRACIÓN CON API (FastAPI)
# ============================================================================

def ejemplo_con_fastapi():
    """Ejemplo de integración con FastAPI"""
    
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    from rag_infrastructure import RAGIngestionPipeline
    import os
    
    app = FastAPI()
    
    # Inicializar pipeline (una vez al inicio)
    pipeline = RAGIngestionPipeline(
        data_directory=os.getenv("DATA_DIRECTORY", "./documents"),
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_password=os.getenv("SUPABASE_DB_PASSWORD"),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
    
    class SearchRequest(BaseModel):
        query: str
        language: str = None
        category: str = None
        top_k: int = 10
    
    @app.post("/ingest")
    async def ingest():
        """Endpoint para ejecutar ingesta"""
        try:
            results = pipeline.ingest()
            return results
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/search")
    async def search(request: SearchRequest):
        """Endpoint para búsqueda"""
        try:
            resultados = pipeline.search(
                query=request.query,
                language=request.language,
                category=request.category,
                top_k=request.top_k
            )
            return {"results": resultados}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # Ejecutar: uvicorn main:app --reload
    return app

# ============================================================================
# OPCIÓN 4: PROCESAMIENTO POR LOTES
# ============================================================================

def ejemplo_procesamiento_lotes():
    """Procesar documentos en lotes con control manual"""
    
    from rag_infrastructure import RAGIngestionPipeline
    from pathlib import Path
    
    pipeline = RAGIngestionPipeline(
        data_directory="./documentos",
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_password=os.getenv("SUPABASE_DB_PASSWORD"),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
    
    # Obtener archivos manualmente
    data_dir = Path("./documentos")
    archivos = list(data_dir.glob("*.pdf"))
    
    # Procesar en lotes de 10
    batch_size = 10
    for i in range(0, len(archivos), batch_size):
        batch = archivos[i:i+batch_size]
        print(f"Procesando lote {i//batch_size + 1} ({len(batch)} archivos)...")
        
        # Aquí podrías procesar cada archivo individualmente
        # o modificar el pipeline para aceptar una lista de archivos
        
        # Por ahora, usar el pipeline completo
        if i == 0:  # Solo ejecutar una vez como ejemplo
            results = pipeline.ingest()
            print(f"Resultados: {results}")

# ============================================================================
# OPCIÓN 5: CONFIGURACIÓN PERSONALIZADA
# ============================================================================

def ejemplo_configuracion_personalizada():
    """Pipeline con configuración completamente personalizada"""
    
    from rag_infrastructure import RAGIngestionPipeline
    
    pipeline = RAGIngestionPipeline(
        data_directory="./mis_docs",
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_password=os.getenv("SUPABASE_DB_PASSWORD"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        
        # Personalización
        collection_name="mi_proyecto_especial",
        chunk_size=2048,                    # Chunks más grandes
        chunk_overlap=400,                  # Más overlap
        embedding_batch_size=50,            # Batches más grandes
        max_workers=20,                     # Más workers
        embedding_model="text-embedding-3-large",  # Modelo diferente
        target_rpm=4000,                    # Más agresivo
        target_tpm=4000000,
        min_chunks_per_file=3,              # Menos estricto
        monitor_update_interval=10          # Actualizaciones cada 10s
    )
    
    # Ejecutar con reindexación forzada
    results = pipeline.ingest(force_reindex=True)

if __name__ == "__main__":
    print("="*80)
    print("EJEMPLOS DE USO DE LA INFRAESTRUCTURA RAG")
    print("="*80)
    
    print("\n1. Uso Simple:")
    print("   ejemplo_uso_simple()")
    
    print("\n2. Uso Modular:")
    print("   ejemplo_uso_modular()")
    
    print("\n3. Con FastAPI:")
    print("   app = ejemplo_con_fastapi()")
    
    print("\n4. Procesamiento por Lotes:")
    print("   ejemplo_procesamiento_lotes()")
    
    print("\n5. Configuración Personalizada:")
    print("   ejemplo_configuracion_personalizada()")
    
    # Descomentar para ejecutar
    # ejemplo_uso_simple()



















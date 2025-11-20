"""
📋 SCRIPT PARA COPIAR LA INFRAESTRUCTURA RAG A OTRO PROYECTO
============================================================

Este script facilita copiar toda la infraestructura RAG a un nuevo proyecto.
"""

import os
import shutil
from pathlib import Path

def copiar_infraestructura(destino: str, incluir_ejemplos: bool = True):
    """
    Copia la infraestructura RAG a un nuevo proyecto
    
    Args:
        destino: Ruta del proyecto destino
        incluir_ejemplos: Si True, incluye archivos de ejemplo
    """
    destino_path = Path(destino)
    
    # Crear directorio destino si no existe
    destino_path.mkdir(parents=True, exist_ok=True)
    
    # Archivos y carpetas a copiar
    items_a_copiar = [
        "rag_infrastructure",
        "anti_duplicates.py",
        "metadata_extractor.py",
        "error_logger.py",
        "rag_search.py",
        "ingestion_monitor.py",
        "config_ingesta.py",
    ]
    
    if incluir_ejemplos:
        items_a_copiar.extend([
            "EJEMPLO_BUSQUEDA_FILTROS.py",
            "EJEMPLO_PROYECTO_NUEVO.py",
            "GUIA_REUTILIZACION.md",
            "README_REUTILIZACION.md",
            "EJEMPLO_ERROR_LOGGING.md",
        ])
    
    print(f"📦 Copiando infraestructura RAG a: {destino_path.absolute()}")
    print("="*80)
    
    # Copiar cada item
    for item in items_a_copiar:
        origen = Path(item)
        if origen.exists():
            if origen.is_dir():
                destino_item = destino_path / item
                if destino_item.exists():
                    print(f"⚠️  {item}/ ya existe, omitiendo...")
                else:
                    shutil.copytree(origen, destino_item)
                    print(f"✅ Copiado: {item}/")
            else:
                destino_item = destino_path / item
                if destino_item.exists():
                    print(f"⚠️  {item} ya existe, omitiendo...")
                else:
                    shutil.copy2(origen, destino_item)
                    print(f"✅ Copiado: {item}")
        else:
            print(f"⚠️  {item} no encontrado, omitiendo...")
    
    # Crear archivo .env.example si no existe
    env_example = destino_path / ".env.example"
    if not env_example.exists():
        env_content = """# Configuración de Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_DB_PASSWORD=tu_password

# Configuración de OpenAI
OPENAI_API_KEY=sk-...

# Directorio de documentos
DATA_DIRECTORY=./documents

# Nombre de la colección vectorial
VECTOR_COLLECTION_NAME=knowledge

# Configuración de ingesta (opcional)
CHUNK_SIZE=1024
CHUNK_OVERLAP=200
EMBEDDING_BATCH_SIZE=30
MAX_WORKERS=15
FORCE_REINDEX=false
"""
        env_example.write_text(env_content, encoding='utf-8')
        print(f"✅ Creado: .env.example")
    
    # Crear requirements.txt si no existe
    requirements = destino_path / "requirements.txt"
    if not requirements.exists():
        req_content = """llama-index>=0.9.0
openai>=1.0.0
psycopg2-binary>=2.9.0
python-dotenv>=1.0.0
rich>=13.0.0

# Opcionales (para mejor extracción de metadatos)
# PyPDF2>=3.0.0
# langdetect>=1.0.9
"""
        requirements.write_text(req_content, encoding='utf-8')
        print(f"✅ Creado: requirements.txt")
    
    # Crear README básico si no existe
    readme = destino_path / "README.md"
    if not readme.exists():
        readme_content = """# Mi Proyecto RAG

Este proyecto usa la infraestructura RAG reutilizable.

## Inicio Rápido

1. Instalar dependencias:
```bash
pip install -r requirements.txt
```

2. Configurar variables de entorno:
```bash
cp .env.example .env
# Editar .env con tus credenciales
```

3. Usar la infraestructura:
```python
from rag_infrastructure import RAGIngestionPipeline

pipeline = RAGIngestionPipeline(
    data_directory="./documents",
    supabase_url="...",
    supabase_password="...",
    openai_api_key="..."
)

pipeline.ingest()
```

Ver `GUIA_REUTILIZACION.md` para más información.
"""
        readme.write_text(readme_content, encoding='utf-8')
        print(f"✅ Creado: README.md")
    
    print("\n" + "="*80)
    print("✅ Infraestructura copiada exitosamente!")
    print(f"\n📁 Ubicación: {destino_path.absolute()}")
    print("\n📝 Próximos pasos:")
    print("   1. cd " + str(destino_path))
    print("   2. pip install -r requirements.txt")
    print("   3. cp .env.example .env")
    print("   4. Editar .env con tus credenciales")
    print("   5. Ver EJEMPLO_PROYECTO_NUEVO.py para empezar")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python copiar_infraestructura.py <ruta_destino> [--sin-ejemplos]")
        print("\nEjemplo:")
        print("  python copiar_infraestructura.py ../mi_nuevo_proyecto")
        print("  python copiar_infraestructura.py ../mi_nuevo_proyecto --sin-ejemplos")
        sys.exit(1)
    
    destino = sys.argv[1]
    incluir_ejemplos = "--sin-ejemplos" not in sys.argv
    
    copiar_infraestructura(destino, incluir_ejemplos)


















"""
Script de configuración inicial para nuevos proyectos.

Este script ayuda a configurar rápidamente un nuevo proyecto basado en esta plantilla.
"""

import os
import sys
import shutil

def print_header(text):
    """Imprime un encabezado formateado"""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60 + "\n")

def crear_configuracion_dominio():
    """Crea un archivo config.py personalizado según el dominio"""
    print_header("CONFIGURACIÓN DEL DOMINIO")
    
    print("Este script te ayudará a configurar tu nuevo proyecto.")
    print("\nEjemplos de dominios:")
    print("  - cocina")
    print("  - psicologia")
    print("  - medicina")
    print("  - educacion")
    print("  - trading")
    print("  - etc.\n")
    
    dominio = input("Ingresa el nombre del dominio/tema: ").strip()
    if not dominio:
        print("❌ El dominio no puede estar vacío")
        return False
    
    # Crear descripción del asistente
    print(f"\nDescribe brevemente qué tipo de asistente será (ej: 'experto en {dominio}'):")
    descripcion = input("Descripción: ").strip()
    if not descripcion:
        descripcion = f"experto en {dominio}"
    
    asistente_desc = f"Eres un asistente {descripcion}. Responde basándote en el contexto proporcionado."
    
    # Crear contenido del config.py
    config_content = f'''"""
Archivo de configuración para personalizar el chatbot según el dominio/tema.

Dominio configurado: {dominio}
"""

# ============================================================================
# CONFIGURACIÓN DEL DOMINIO/TEMA
# ============================================================================

# Nombre del dominio/tema de tu proyecto
DOMAIN_NAME = "{dominio}"

# Descripción del asistente (se usa en el prompt del sistema)
ASSISTANT_DESCRIPTION = "{asistente_desc}"

# Título de la API (aparece en la documentación de FastAPI)
API_TITLE = "Chat Bot API - {dominio.capitalize()}"

# Descripción de la API
API_DESCRIPTION = "API para consultar documentos indexados sobre {dominio} con sistema de tokens"

# Nombre de la colección de vectores en Supabase
# Puedes usar el mismo nombre para todos los proyectos o cambiarlo por dominio
VECTOR_COLLECTION_NAME = "knowledge"

# Carpeta donde están los documentos a indexar
DATA_DIRECTORY = "./data"

# ============================================================================
# CONFIGURACIÓN AVANZADA (opcional)
# ============================================================================

# Número de documentos similares a recuperar para el contexto
SIMILARITY_TOP_K = 5

# Temperatura del modelo (creatividad: 0.0 = conservador, 1.0 = creativo)
MODEL_TEMPERATURE = 0.7

# Tokens iniciales para nuevos usuarios
INITIAL_TOKENS = 20000
'''
    
    # Guardar config.py
    try:
        with open("config.py", "w", encoding="utf-8") as f:
            f.write(config_content)
        print(f"\n✅ Archivo config.py creado exitosamente para dominio: {dominio}")
        return True
    except Exception as e:
        print(f"\n❌ Error al crear config.py: {e}")
        return False

def crear_env_ejemplo():
    """Crea un archivo .env de ejemplo si no existe"""
    if os.path.exists(".env"):
        print("⚠️  El archivo .env ya existe. No se sobrescribirá.")
        return
    
    if os.path.exists("env.example.txt"):
        try:
            shutil.copy("env.example.txt", ".env")
            print("✅ Archivo .env creado desde env.example.txt")
            print("⚠️  IMPORTANTE: Edita .env y completa con tus credenciales reales")
        except Exception as e:
            print(f"⚠️  No se pudo crear .env: {e}")
    else:
        print("⚠️  No se encontró env.example.txt")

def crear_carpeta_data():
    """Crea la carpeta data si no existe"""
    if not os.path.exists("data"):
        try:
            os.makedirs("data")
            print("✅ Carpeta 'data' creada")
            print("   Coloca tus documentos (PDFs, EPUBs, etc.) en esta carpeta")
        except Exception as e:
            print(f"⚠️  No se pudo crear la carpeta data: {e}")
    else:
        print("✅ La carpeta 'data' ya existe")

def main():
    """Función principal"""
    print_header("SETUP DE NUEVO PROYECTO")
    
    print("Este script configurará tu proyecto para un nuevo dominio.")
    print("Asegúrate de estar en la carpeta del proyecto antes de continuar.\n")
    
    respuesta = input("¿Deseas continuar? (s/n): ").strip().lower()
    if respuesta != 's':
        print("Operación cancelada.")
        return
    
    # Paso 1: Configurar dominio
    if not crear_configuracion_dominio():
        print("\n❌ Error en la configuración. Abortando.")
        return
    
    # Paso 2: Crear .env
    print("\n" + "-" * 60)
    crear_env_ejemplo()
    
    # Paso 3: Crear carpeta data
    print("\n" + "-" * 60)
    crear_carpeta_data()
    
    # Resumen final
    print_header("CONFIGURACIÓN COMPLETADA")
    
    print("✅ Configuración básica completada!")
    print("\nPróximos pasos:")
    print("1. Edita el archivo .env y completa con tus credenciales de Supabase")
    print("2. Ejecuta los scripts SQL en Supabase:")
    print("   - create_profiles_table.sql")
    print("   - create_conversations_table.sql")
    print("3. Coloca tus documentos en la carpeta ./data")
    print("4. Ejecuta: python ingest_improved.py")
    print("5. Inicia el servidor: python main.py")
    print("\n¡Listo para comenzar! 🚀")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperación cancelada por el usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        sys.exit(1)


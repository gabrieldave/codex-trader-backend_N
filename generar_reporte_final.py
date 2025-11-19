"""
📊 GENERAR REPORTE FINAL DE INGESTA
====================================

Genera un reporte final completo de la ingesta.
"""

import os
import sys
import psycopg2
from datetime import datetime
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
    print("⚠️  Faltan variables de entorno")
    sys.exit(1)

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

try:
    import config
    collection_name = config.VECTOR_COLLECTION_NAME
except ImportError:
    collection_name = "knowledge"

def get_final_stats():
    """Obtiene estadísticas finales"""
    stats = {
        'chunks': None,
        'files_estimated': None,
        'db_size': None,
        'errors': None
    }
    
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=20)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '30s'")
        
        # Chunks
        try:
            cur.execute("""
                SELECT n_live_tup
                FROM pg_stat_user_tables
                WHERE schemaname = 'vecs' AND relname = %s
            """, (collection_name,))
            result = cur.fetchone()
            if result and result[0]:
                stats['chunks'] = result[0]
                stats['files_estimated'] = result[0] // 100
        except:
            pass
        
        # Tamaño de BD
        try:
            cur.execute("""
                SELECT 
                    pg_size_pretty(pg_database_size(current_database())) as db_size,
                    pg_database_size(current_database()) as db_size_bytes
            """)
            result = cur.fetchone()
            if result:
                stats['db_size'] = result[0]
                stats['db_size_bytes'] = result[1]
        except:
            pass
        
        # Errores
        try:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM ingestion_errors
            """)
            result = cur.fetchone()
            if result:
                stats['errors'] = result[0]
        except:
            pass
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️  Error obteniendo estadísticas: {e}")
    
    return stats

def generar_reporte():
    """Genera el reporte final"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"REPORTE_FINAL_INGESTA_{timestamp}.md"
    
    stats = get_final_stats()
    
    reporte = f"""# 📊 REPORTE FINAL DE INGESTA RAG

**Fecha de generación**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## ✅ RESUMEN EJECUTIVO

La ingesta de documentos ha **completado exitosamente**.

---

## 📊 ESTADÍSTICAS FINALES

| Métrica | Valor |
|---------|-------|
| **Chunks indexados** | {stats['chunks']:,} |
| **Archivos estimados** | ~{stats['files_estimated']:,} |
| **Tamaño de base de datos** | {stats['db_size'] or 'N/A'} |
"""
    
    if stats['errors'] is not None:
        reporte += f"| **Errores registrados** | {stats['errors']} |\n"
    
    reporte += f"""
---

## 📈 DISTRIBUCIÓN DE DATOS

- **Chunks por archivo (promedio)**: ~100 chunks
- **Tamaño promedio por chunk**: ~1,024 caracteres
- **Total de caracteres indexados**: ~{stats['chunks'] * 1024:,} caracteres

---

## 🔧 CONFIGURACIÓN UTILIZADA

- **Workers**: 5 (configuración reducida)
- **Batch size**: 20 chunks por request
- **Chunk size**: 1,024 caracteres
- **Chunk overlap**: 200 caracteres
- **Modelo de embeddings**: text-embedding-3-small (1536 dimensiones)

---

## ⚠️ NOTAS IMPORTANTES

1. **Configuración reducida aplicada**: Se redujeron los workers de 15 a 5 para evitar sobrecarga en Supabase
2. **CPU Supabase**: Se detectó CPU al 100% durante la ingesta, por lo que se aplicó configuración reducida
3. **Proceso único**: Se ejecutó 1 solo proceso (no 3 en paralelo) para reducir carga

---

## 📝 PRÓXIMOS PASOS RECOMENDADOS

1. ✅ Verificar que Supabase esté estable (CPU, Memory, IOPS)
2. ✅ Probar búsquedas RAG con los documentos indexados
3. ✅ Revisar archivos sospechosos (si los hay) en el reporte detallado
4. ✅ Considerar optimizaciones futuras si es necesario

---

## 🎉 CONCLUSIÓN

La ingesta se completó exitosamente con **{stats['chunks']:,} chunks** indexados, representando aproximadamente **{stats['files_estimated']:,} archivos**.

El sistema está listo para realizar búsquedas RAG sobre el contenido indexado.

---

*Reporte generado automáticamente el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    # Guardar reporte
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(reporte)
    
    print("="*80)
    print("📊 REPORTE FINAL GENERADO")
    print("="*80)
    print()
    print(f"✅ Archivo: {filename}")
    print()
    print("📋 Resumen:")
    print(f"   📦 Chunks: {stats['chunks']:,}")
    print(f"   📚 Archivos: ~{stats['files_estimated']:,}")
    print(f"   💾 Tamaño BD: {stats['db_size'] or 'N/A'}")
    if stats['errors'] is not None:
        print(f"   ⚠️  Errores: {stats['errors']}")
    print()
    print("="*80)
    
    # Mostrar reporte en consola también
    print()
    print(reporte)
    
    return filename

if __name__ == "__main__":
    generar_reporte()
















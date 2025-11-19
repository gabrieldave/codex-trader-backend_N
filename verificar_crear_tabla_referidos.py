"""
Script para verificar y crear la tabla referral_reward_events en Supabase.
Este script verifica si la tabla existe y la crea si no existe.
"""
import os
import sys
from urllib.parse import quote_plus

def get_env(key):
    """Obtiene variable de entorno limpiando comillas"""
    value = os.environ.get(key)
    if value is None:
        return None
    return value.strip('"').strip("'").strip()

# Intentar cargar desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Obtener variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("ERROR: Faltan variables de entorno SUPABASE_URL o SUPABASE_DB_PASSWORD")
    print("   Asegurate de tener estas variables configuradas en tu entorno")
    print("   o en un archivo .env en el directorio del proyecto")
    sys.exit(1)

# Construir cadena de conexión PostgreSQL
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("=" * 70)
print("VERIFICANDO Y CREANDO TABLA referral_reward_events")
print("=" * 70)
print()

try:
    import psycopg2
    
    # Conectar a la base de datos
    print("Conectando a Supabase...")
    conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
    conn.autocommit = False  # Usar transacciones
    cur = conn.cursor()
    print("OK: Conexión establecida\n")
    
    # Verificar si la tabla existe
    print("1. Verificando si la tabla referral_reward_events existe...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'referral_reward_events'
        )
    """)
    table_exists = cur.fetchone()[0]
    
    if table_exists:
        print("   ✅ La tabla referral_reward_events ya existe")
        print()
        
        # Verificar estructura de la tabla
        print("2. Verificando estructura de la tabla...")
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'referral_reward_events'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        
        expected_columns = {
            'id': 'uuid',
            'invoice_id': 'text',
            'user_id': 'uuid',
            'referrer_id': 'uuid',
            'reward_type': 'text',
            'tokens_granted': 'bigint',
            'created_at': 'timestamp with time zone'
        }
        
        actual_columns = {col[0]: col[1] for col in columns}
        missing_columns = set(expected_columns.keys()) - set(actual_columns.keys())
        
        if missing_columns:
            print(f"   ⚠️ ADVERTENCIA: Faltan columnas: {', '.join(missing_columns)}")
        else:
            print("   ✅ Estructura de la tabla correcta")
            for col_name, col_type in columns:
                print(f"      - {col_name}: {col_type}")
        
        # Verificar índices
        print()
        print("3. Verificando índices...")
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' 
            AND tablename = 'referral_reward_events'
        """)
        indexes = [row[0] for row in cur.fetchall()]
        
        expected_indexes = [
            'referral_reward_events_invoice_id_idx',
            'referral_reward_events_user_id_idx',
            'referral_reward_events_referrer_id_idx'
        ]
        
        missing_indexes = [idx for idx in expected_indexes if idx not in indexes]
        if missing_indexes:
            print(f"   ⚠️ ADVERTENCIA: Faltan índices: {', '.join(missing_indexes)}")
            print("   Creando índices faltantes...")
            
            if 'referral_reward_events_invoice_id_idx' in missing_indexes:
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS referral_reward_events_invoice_id_idx 
                    ON public.referral_reward_events(invoice_id)
                """)
            
            if 'referral_reward_events_user_id_idx' in missing_indexes:
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS referral_reward_events_user_id_idx 
                    ON public.referral_reward_events(user_id)
                """)
            
            if 'referral_reward_events_referrer_id_idx' in missing_indexes:
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS referral_reward_events_referrer_id_idx 
                    ON public.referral_reward_events(referrer_id)
                """)
            
            conn.commit()
            print("   ✅ Índices creados")
        else:
            print("   ✅ Todos los índices existen")
            for idx in indexes:
                print(f"      - {idx}")
    else:
        print("   ❌ La tabla referral_reward_events NO existe")
        print()
        print("2. Creando la tabla referral_reward_events...")
        
        # Crear la tabla
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS public.referral_reward_events (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          invoice_id TEXT UNIQUE NOT NULL,
          user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
          referrer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
          reward_type TEXT NOT NULL,
          tokens_granted BIGINT NOT NULL,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
        )
        """
        
        cur.execute(create_table_sql)
        print("   ✅ Tabla creada")
        
        # Crear índices
        print()
        print("3. Creando índices...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS referral_reward_events_invoice_id_idx 
            ON public.referral_reward_events(invoice_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS referral_reward_events_user_id_idx 
            ON public.referral_reward_events(user_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS referral_reward_events_referrer_id_idx 
            ON public.referral_reward_events(referrer_id)
        """)
        print("   ✅ Índices creados")
        
        conn.commit()
        print()
        print("✅ Tabla y índices creados exitosamente")
    
    # Verificar columna has_generated_referral_reward en profiles
    print()
    print("4. Verificando columna has_generated_referral_reward en profiles...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'profiles'
            AND column_name = 'has_generated_referral_reward'
        )
    """)
    column_exists = cur.fetchone()[0]
    
    if column_exists:
        print("   ✅ Columna has_generated_referral_reward existe")
    else:
        print("   ⚠️ Columna has_generated_referral_reward NO existe")
        print("   Creando columna...")
        cur.execute("""
            ALTER TABLE public.profiles 
            ADD COLUMN IF NOT EXISTS has_generated_referral_reward BOOLEAN DEFAULT FALSE
        """)
        conn.commit()
        print("   ✅ Columna creada")
    
    # Resumen final
    print()
    print("=" * 70)
    print("RESUMEN:")
    print("=" * 70)
    print("✅ Sistema de referidos configurado correctamente")
    print("   - Tabla referral_reward_events: Lista")
    print("   - Índices: Creados")
    print("   - Columna has_generated_referral_reward: Lista")
    print()
    print("El sistema de recompensas de referidos está listo para funcionar.")
    
    cur.close()
    conn.close()
    
except ImportError:
    print("ERROR: psycopg2 no está instalado")
    print("   Instala con: pip install psycopg2-binary")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


# 🛠️ SCRIPTS ÚTILES DEL PROYECTO

## 📋 Resumen de Scripts Disponibles

### **Scripts de Ingesta (Mantener)**

#### ✅ Scripts Principales
- **`ingest_optimized_rag.py`** ⭐ **PRINCIPAL**
  - Pipeline optimizado completo
  - Sistema anti-duplicados
  - Monitor en tiempo real
  - Control de rate limits al 70% de Tier 3
  - **Uso**: `python ingest_optimized_rag.py`

- **`ingest_optimized_tier3.py`**
  - Optimizado específicamente para Tier 3
  - Procesamiento paralelo (hasta 10 workers)
  - Batch size optimizado (32-64 archivos)
  - **Uso**: Para procesamiento masivo con Tier 3

- **`ingest_parallel_tier3.py`**
  - Versión paralela para Tier 3
  - Workers configurables (5, 10, 20...)
  - Control automático de rate limits
  - **Uso**: Para máxima velocidad con Tier 3

#### ⚙️ Scripts de Configuración
- **`config_ingesta.py`**
  - Configuración centralizada de ingesta
  - Parámetros ajustables mediante variables de entorno

- **`config_ingesta_reducida.py`**
  - Configuración reducida para evitar sobrecarga
  - Workers: 5, Batch: 20

#### 🛡️ Scripts de Seguridad
- **`iniciar_ingesta_segura.py`**
  - Previene ejecuciones múltiples
  - Verifica procesos activos antes de iniciar

- **`detener_ingesta_emergencia.py`**
  - Detiene todos los procesos de ingesta inmediatamente
  - Útil en caso de sobrecarga

- **`kill_ingest_processes.py`**
  - Termina procesos de ingesta activos
  - Muestra información de procesos antes de terminar

---

### **Scripts de Verificación y Monitoreo**

#### ✅ Verificación de Estado
- **`check_status.py`**
  - Verifica estado del sistema
  - Procesos activos, memoria, CPU
  - **Uso**: `python check_status.py`

- **`check_ingest_running.py`**
  - Verifica si hay procesos de ingesta corriendo
  - **Uso**: Antes de iniciar nueva ingesta

- **`check_ingest_errors.py`**
  - Verifica errores en la ingesta
  - Consulta tabla `ingestion_errors`

#### 📊 Verificación de Datos
- **`check_new_files.py`**
  - Verifica archivos nuevos que necesitan ser procesados
  - Compara archivos locales con indexados
  - **Uso**: `python check_new_files.py`

- **`check_duplicates.py`**
  - Verifica duplicados en la base de datos
  - Analiza tabla `documents`
  - **Uso**: `python check_duplicates.py`

- **`view_data.py`**
  - Visualiza datos en Supabase
  - Chunks, documentos, estadísticas
  - **Uso**: `python view_data.py`

- **`check_vecs_data.py`**
  - Verifica datos en la colección de vectores
  - **Uso**: `python check_vecs_data.py`

- **`check_table.py`**
  - Verifica estructura de tablas
  - **Uso**: `python check_table.py`

#### 📈 Estadísticas y Conteo
- **`contar_indexados.py`**
  - Cuenta documentos y chunks indexados
  - **Uso**: `python contar_indexados.py`

- **`contar_indexados_rapido.py`**
  - Versión rápida del conteo
  - **Uso**: `python contar_indexados_rapido.py`

- **`contar_final.py`**
  - Conteo final con estadísticas completas
  - **Uso**: `python contar_final.py`

- **`contar_estadisticas.py`**
  - Estadísticas detalladas de la ingesta
  - **Uso**: `python contar_estadisticas.py`

---

### **Scripts de Utilidad**

#### 🔧 Configuración y Setup
- **`configurar_deepseek.py`**
  - Configura DeepSeek como modelo de chat
  - **Uso**: `python configurar_deepseek.py`

- **`verificar_configuracion_deepseek.py`**
  - Verifica configuración de DeepSeek
  - **Uso**: `python verificar_configuracion_deepseek.py`

#### 📧 Emails y Auditoría
- **`test_emails_audit.py`** ⭐ **ÚTIL**
  - Prueba todos los emails del sistema
  - Auditoría completa de templates
  - **Uso**: `python test_emails_audit.py`

- **`test_greeting_detection.py`**
  - Prueba detección de saludos
  - **Uso**: `python test_greeting_detection.py`

- **`test_referral_flow.py`**
  - Prueba flujo de referidos
  - **Uso**: `python test_referral_flow.py`

#### 🔍 Verificación de Límites
- **`verificar_limites_openai.py`**
  - Verifica límites de OpenAI
  - **Uso**: `python verificar_limites_openai.py`

- **`verificar_limites_supabase.py`**
  - Verifica límites y uso de Supabase
  - **Uso**: `python verificar_limites_supabase.py`

#### 📊 Monitoreo y Progreso
- **`barra_progreso_ingesta.py`**
  - Barra de progreso visual para ingesta
  - **Uso**: `python barra_progreso_ingesta.py`

- **`check_progress_now.py`**
  - Verifica progreso actual de la ingesta
  - **Uso**: `python check_progress_now.py`

- **`medir_velocidad_y_eta.py`**
  - Mide velocidad y calcula ETA
  - **Uso**: `python medir_velocidad_y_eta.py`

#### 🗄️ Base de Datos
- **`verify_data.py`**
  - Verifica integridad de datos
  - **Uso**: `python verify_data.py`

- **`verify_indexing.py`**
  - Verifica que la indexación sea correcta
  - **Uso**: `python verify_indexing.py`

- **`verify_profiles.py`**
  - Verifica perfiles de usuarios
  - **Uso**: `python verify_profiles.py`

#### 🔄 Gestión de Procesos
- **`detener_todos_procesos.py`**
  - Detiene todos los procesos Python
  - **Uso**: `python detener_todos_procesos.py`

- **`kill_all_python.py`**
  - Termina todos los procesos Python
  - **Uso**: `python kill_all_python.py`

- **`wait_for_ingest.py`**
  - Espera a que termine la ingesta
  - **Uso**: `python wait_for_ingest.py`

---

### **Scripts de Desarrollo y Testing**

#### 🧪 Testing
- **`quick_check.py`**
  - Verificación rápida del sistema
  - **Uso**: `python quick_check.py`

- **`diagnostico_profundo.py`**
  - Diagnóstico completo del sistema
  - **Uso**: `python diagnostico_profundo.py`

#### 🔧 Utilidades
- **`update_batch_size.py`**
  - Actualiza batch size dinámicamente
  - **Uso**: `python update_batch_size.py`

- **`recreate_index_safe.py`**
  - Recrea índice de forma segura
  - **Uso**: `python recreate_index_safe.py`

- **`delete_collection.py`**
  - Elimina colección de vectores
  - **Uso**: `python delete_collection.py`

- **`create_fix_index.py`**
  - Crea o repara índices
  - **Uso**: `python create_fix_index.py`

---

### **Scripts de Información y Consulta**

#### 📊 Tokens y Uso
- **`consultar_tokens_usados.py`**
  - Consulta tokens usados por usuarios
  - **Uso**: `python consultar_tokens_usados.py`

- **`ver_logs_tokens.py`**
  - Ver logs de tokens
  - **Uso**: `python ver_logs_tokens.py`

- **`ver_tokens_ultimas_consultas.py`**
  - Ver tokens de últimas consultas
  - **Uso**: `python ver_tokens_ultimas_consultas.py`

#### 📈 Reportes
- **`generar_reporte_final.py`**
  - Genera reporte final de ingesta
  - **Uso**: `python generar_reporte_final.py`

---

### **Scripts de Infraestructura**

#### 🔄 Reutilización
- **`copiar_infraestructura.py`**
  - Copia infraestructura RAG a nuevo proyecto
  - **Uso**: `python copiar_infraestructura.py <ruta_destino>`

- **`setup_nuevo_proyecto.py`**
  - Configura nuevo proyecto
  - **Uso**: `python setup_nuevo_proyecto.py`

---

## 🎯 Scripts Más Utilizados

### **Para Iniciar Ingesta**
```bash
python iniciar_ingesta_segura.py
# o directamente
python ingest_optimized_rag.py
```

### **Para Verificar Estado**
```bash
python check_status.py
python check_ingest_running.py
python contar_indexados.py
```

### **Para Verificar Datos**
```bash
python check_new_files.py
python check_duplicates.py
python view_data.py
```

### **Para Detener Procesos**
```bash
python detener_ingesta_emergencia.py
# o
python kill_ingest_processes.py
```

### **Para Auditoría**
```bash
python test_emails_audit.py
python verificar_limites_openai.py
python verificar_limites_supabase.py
```

---

## ⚠️ Scripts Eliminados (Ya No Existen)

- ❌ `ingest.py` - Versión antigua
- ❌ `ingest_improved.py` - Versión antigua
- ❌ `monitor_*.py` (múltiples versiones) - Solo se mantiene `ingestion_monitor.py`
- ❌ `verificar_*.py` (múltiples versiones) - Solo se mantienen los esenciales

---

## 📝 Notas

- **Script Principal**: `ingest_optimized_rag.py` es el script principal para ingesta
- **Configuración**: Todos los scripts usan variables de entorno del archivo `.env`
- **Monitoreo**: `ingestion_monitor.py` es el monitor oficial integrado
- **Seguridad**: Siempre usar `iniciar_ingesta_segura.py` o verificar con `check_ingest_running.py` antes de iniciar

---

*Última actualización: Enero 2025*




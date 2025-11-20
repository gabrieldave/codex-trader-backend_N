# Guía: Configurar Reporte Automático con GitHub Actions

Este documento explica cómo configurar el reporte de proyecciones para que se ejecute automáticamente todos los días usando GitHub Actions.

## Paso 1: Configurar Secrets en GitHub

1. Ve a tu repositorio en GitHub: `https://github.com/gabrieldave/codex-trader-backend_N`

2. Haz clic en **Settings** (arriba a la derecha del repositorio)

3. En el menú lateral izquierdo, busca y haz clic en **Secrets and variables** → **Actions**

4. Haz clic en el botón verde **"New repository secret"**

5. Crea los siguientes secrets (uno por uno):

   **Secret 1: SUPABASE_REST_URL**
   - Name: `SUPABASE_REST_URL`
   - Secret: `https://hozhzyzdurdpkjoehqrh.supabase.co`
   - Haz clic en **"Add secret"**

   **Secret 2: SUPABASE_SERVICE_KEY**
   - Name: `SUPABASE_SERVICE_KEY`
   - Secret: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhvemh5emR1cmRvcGtqb2VocXJoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MzI2MDQ4MCwiZXhwIjoyMDc4ODM2NDgwfQ.NSZKmRtxMlfyeslTjfti-YFJg6q8cgHFyaHj-rkQwpg`
   - Haz clic en **"Add secret"**

6. Verifica que ambos secrets aparezcan en la lista (aparecerán como `*******` por seguridad)

## Paso 2: Verificar que el Workflow esté creado

El archivo `.github/workflows/proyecciones.yml` ya está creado en el repositorio. Solo necesitas hacer commit y push:

```bash
git add .github/workflows/proyecciones.yml
git commit -m "feat: agregar workflow de reporte automático"
git push
```

## Paso 3: Probar el Workflow

1. Ve a la pestaña **Actions** en tu repositorio de GitHub

2. Deberías ver el workflow **"Reporte de Proyecciones Diario"** en la lista

3. Haz clic en el workflow y luego en **"Run workflow"** (botón a la derecha)

4. Selecciona la rama `main` y haz clic en **"Run workflow"**

5. Espera unos minutos y verás el resultado en los logs

## Paso 4: Ver los Resultados

Después de que el workflow se ejecute:

1. Ve a la pestaña **Actions**

2. Haz clic en la ejecución más reciente del workflow

3. Expande el paso **"Ejecutar script de proyecciones"** para ver el reporte completo en los logs

4. En la sección **Artifacts** (al final de la página), podrás descargar el archivo `reporte-proyecciones-YYYYMMDD.txt` con el reporte completo

## Configuración del Horario

El workflow está configurado para ejecutarse **todos los días a las 10:00 AM UTC**.

- **UTC-6 (México)**: 10:00 UTC = 4:00 AM hora local
- Si quieres que se ejecute a las 10:00 AM hora local (México), el cron debería ser: `0 16 * * *`

Para cambiar la hora, edita el archivo `.github/workflows/proyecciones.yml` y modifica la línea:
```yaml
- cron: '0 10 * * *'  # Cambia el primer número (0-23) para la hora UTC
```

## Ejecución Manual

También puedes ejecutar el workflow manualmente en cualquier momento:
1. Ve a **Actions** → **Reporte de Proyecciones Diario**
2. Haz clic en **"Run workflow"**
3. Selecciona la rama y ejecuta

## Solución de Problemas

Si el workflow falla:

1. Revisa los logs en la pestaña **Actions**
2. Verifica que los secrets estén configurados correctamente
3. Asegúrate de que las dependencias en `requirements.txt` estén actualizadas


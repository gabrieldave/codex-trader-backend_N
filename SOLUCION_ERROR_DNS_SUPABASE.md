# Solución: Error "Name or service not known" al iniciar sesión

## Problema

El backend no puede conectarse a Supabase, mostrando el error:
```
[Errno -2] Name or service not known
```

Esto impide que los usuarios inicien sesión porque no se pueden validar los tokens.

## Causa

El backend no puede resolver el hostname de Supabase. Esto generalmente ocurre cuando:
1. `SUPABASE_REST_URL` no está configurada en Railway
2. La URL está mal formateada
3. El backend está intentando derivar la URL desde `SUPABASE_DB_URL` y falla

## Solución

### Paso 1: Verificar Variables en Railway

1. Ve a tu proyecto en Railway: https://railway.app
2. Selecciona el servicio `codex-trader-backend`
3. Ve a la pestaña **Variables**
4. Verifica que existan estas variables:

   **OBLIGATORIA:**
   - `SUPABASE_REST_URL` = `https://hozhzyzdurdpkjoehqrh.supabase.co`
   
   **OBLIGATORIA:**
   - `SUPABASE_SERVICE_KEY` = (tu service key completa)

### Paso 2: Agregar/Corregir SUPABASE_REST_URL

Si `SUPABASE_REST_URL` no existe o está mal configurada:

1. En Railway, dentro de **Variables**, haz clic en **"+ New Variable"**
2. Nombre: `SUPABASE_REST_URL`
3. Valor: `https://hozhzyzdurdpkjoehqrh.supabase.co`
4. Guarda

### Paso 3: Reiniciar el Servicio

Después de agregar/corregir la variable:

1. Ve a la pestaña **Deployments**
2. Haz clic en el menú de tres puntos (⋯) del deployment activo
3. Selecciona **"Restart"**
4. Espera a que el servicio se reinicie

### Paso 4: Verificar los Logs

1. Ve a la pestaña **Logs**
2. Busca el mensaje: `🔗 Intentando conectar a Supabase con URL: https://...`
3. Deberías ver: `✅ Conexión a Supabase verificada exitosamente`

Si ves errores, verifica que:
- La URL no tenga espacios al inicio o final
- La URL empiece con `https://`
- El hostname sea correcto: `hozhzyzdurdpkjoehqrh.supabase.co`

## Verificación

Después de reiniciar, intenta iniciar sesión desde el frontend. Si el problema persiste:

1. Revisa los logs de Railway para ver el error exacto
2. Verifica que todas las variables estén correctamente configuradas
3. Asegúrate de que no haya caracteres especiales o espacios en las variables

## Nota Importante

**NO** uses `SUPABASE_DB_URL` para la autenticación. El backend necesita `SUPABASE_REST_URL` directamente configurada. Si solo tienes `SUPABASE_DB_URL`, el backend intentará derivar la URL REST, pero esto puede fallar si la URL de Postgres está mal formateada.


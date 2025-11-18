# 🔧 Solucionar Error de Railway - mise ERROR 500

## ❌ Error Detectado

```
mise ERROR HTTP status server error (500 Internal Server Error) 
for url (https://mise-versions.jdx.dev/python-precompiled-x86_64-unknown-linux-gnu.gz)
```

Railway está usando **Railpack** (su nuevo sistema de build) y está fallando al intentar descargar Python desde mise.

---

## ✅ Soluciones

### Solución 1: Actualizar runtime.txt (Recomendado)

El formato de `runtime.txt` debe ser exacto. Actualiza el archivo:

```txt
python-3.12.12
```

O usa solo la versión mayor y menor:

```txt
3.12.12
```

**Pasos:**
1. Actualiza `runtime.txt` con el formato correcto
2. Haz commit y push
3. Railway debería detectar el cambio y reconstruir

---

### Solución 2: Usar Dockerfile (Más Control)

Crea un `Dockerfile` en la raíz del proyecto:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema si es necesario
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
COPY requirements.ingest.txt .

# Instalar dependencias de Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Exponer puerto
EXPOSE $PORT

# Comando para iniciar la aplicación
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Pasos:**
1. Crea el `Dockerfile` con el contenido arriba
2. Railway detectará el Dockerfile y lo usará en lugar de Railpack
3. Haz commit y push

---

### Solución 3: Actualizar nixpacks.toml

Actualiza tu `nixpacks.toml` para forzar el uso de Nixpacks en lugar de Railpack:

```toml
[phases.setup]
nixPkgs = ["python312"]

[phases.install]
cmds = [
  "pip install --upgrade pip",
  "pip install --no-cache-dir -r requirements.txt"
]

[start]
cmd = "uvicorn main:app --host 0.0.0.0 --port $PORT"

[variables]
PYTHON_VERSION = "3.12"
```

**Nota:** Si tienes `nixpacks.toml`, Railway debería usar Nixpacks en lugar de Railpack. Si sigue usando Railpack, verifica que el archivo esté en la raíz del proyecto.

---

### Solución 4: Forzar Rebuild en Railway

1. Ve a Railway Dashboard → Tu Proyecto
2. Ve a **Settings** → **Build**
3. Haz clic en **"Clear Build Cache"**
4. Haz clic en **"Redeploy"** o **"Deploy Latest Commit"**

Esto fuerza un rebuild completo y puede resolver problemas de caché.

---

### Solución 5: Usar Python 3.11 (Temporal)

Si el problema persiste con Python 3.12, puedes temporalmente usar 3.11:

1. Actualiza `runtime.txt`:
   ```txt
   python-3.11
   ```

2. Actualiza `nixpacks.toml`:
   ```toml
   [phases.setup]
   nixPkgs = ["python311"]
   ```

3. Haz commit y push

---

## 🔍 Verificar Configuración Actual

### 1. Verificar runtime.txt

Asegúrate de que `runtime.txt` tenga exactamente este contenido (sin espacios extra):

```txt
python-3.12.12
```

O:

```txt
3.12.12
```

### 2. Verificar nixpacks.toml

Asegúrate de que `nixpacks.toml` esté en la raíz del proyecto y tenga el formato correcto.

### 3. Verificar que no haya .railwayignore

Si tienes un archivo `.railwayignore`, verifica que no esté ignorando archivos importantes.

---

## 🎯 Solución Recomendada (Paso a Paso)

1. **Actualiza runtime.txt:**
   ```txt
   python-3.12.12
   ```

2. **Verifica nixpacks.toml** (ya lo tienes, debería funcionar)

3. **Haz commit y push:**
   ```bash
   git add runtime.txt
   git commit -m "Fix: Actualizar runtime.txt para Railway"
   git push
   ```

4. **En Railway Dashboard:**
   - Ve a tu proyecto
   - Haz clic en **"Redeploy"** o espera el deploy automático
   - Si persiste, haz **"Clear Build Cache"** → **"Redeploy"**

5. **Si el problema continúa, crea un Dockerfile:**
   - Usa el Dockerfile de la Solución 2
   - Esto fuerza Railway a usar Docker en lugar de Railpack

---

## 🐛 Si el Problema Persiste

### Error: "mise ERROR" continúa

**Solución:** Crea un `Dockerfile` (Solución 2). Docker es más confiable que Railpack para builds complejos.

### Error: "Module not found" después del deploy

**Causa:** Falta instalar alguna dependencia o problema con requirements.txt

**Solución:**
1. Verifica que `requirements.txt` incluya todas las dependencias
2. Prueba localmente: `pip install -r requirements.txt`
3. Si funciona localmente pero no en Railway, puede ser un problema de índices. Verifica que `requirements.txt` no tenga problemas con los índices de PyTorch.

### Error: "PORT not found"

**Causa:** Railway proporciona `$PORT` automáticamente, pero a veces hay problemas.

**Solución en Dockerfile:**
```dockerfile
ENV PORT=8080
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
```

---

## 📝 Nota sobre Railway Build Systems

Railway usa diferentes sistemas de build según los archivos que detecte:

1. **Dockerfile** → Usa Docker (más control, recomendado para proyectos complejos)
2. **nixpacks.toml** → Usa Nixpacks (bueno para Python/Node)
3. **Sin Dockerfile ni nixpacks.toml** → Usa Railpack (nuevo, a veces tiene problemas)

Si tienes problemas con Railpack, crear un `Dockerfile` es la solución más confiable.

---

## ✅ Checklist

- [ ] `runtime.txt` actualizado con formato correcto
- [ ] `nixpacks.toml` presente y correcto (o `Dockerfile` creado)
- [ ] Build cache limpiado en Railway
- [ ] Redeploy realizado
- [ ] Logs verificados para confirmar que funciona

---

## 🚀 Resumen Rápido

**Problema:** Railway/Railpack no puede descargar Python 3.12 desde mise.

**Solución más rápida:**
1. Actualiza `runtime.txt` a `python-3.12.12`
2. Limpia cache en Railway → Redeploy

**Solución más confiable:**
1. Crea un `Dockerfile` (usar el de arriba)
2. Railway usará Docker en lugar de Railpack
3. Haz commit y push

¡Con esto deberías poder desplegar sin problemas! 🎉


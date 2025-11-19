# 📧 Guía: Configuración de Resend

## ✅ Implementación Completada

Resend ha sido implementado como método principal para envío de emails. SMTP se mantiene como fallback.

---

## 🚀 Pasos para Configurar Resend

### 1. Crear Cuenta en Resend

1. Ve a [resend.com](https://resend.com)
2. Crea una cuenta (gratis)
3. Verifica tu email

### 2. Obtener API Key

1. En el dashboard de Resend, ve a **API Keys**
2. Haz clic en **Create API Key**
3. Dale un nombre (ej: "Codex Trader Production")
4. Copia la API key (empieza con `re_`)

### 3. Configurar en Railway

1. Ve a Railway Dashboard → Tu Proyecto → Variables
2. Agrega nueva variable:
   - **Nombre:** `RESEND_API_KEY`
   - **Valor:** `re_xxxxxxxxxxxxx` (tu API key)
3. Guarda los cambios
4. Railway reiniciará automáticamente el servicio

### 4. Verificar Dominio (Opcional)

**Para usar tu dominio personalizado:**
1. En Resend Dashboard → Domains
2. Agrega tu dominio (ej: `codextrader.tech`)
3. Configura los registros DNS que Resend te indique
4. Espera verificación (puede tardar unos minutos)

**Para empezar rápido (sin dominio):**
- Resend te da un dominio de prueba: `onboarding@resend.dev`
- Puedes usarlo para pruebas, pero es mejor configurar tu dominio

---

## 🔧 Cómo Funciona

### Prioridad de Envío:

1. **Resend (si está configurado)** ✅
   - Funciona en Railway
   - API REST (no requiere puertos abiertos)
   - Más rápido y confiable

2. **SMTP (fallback)** ⚠️
   - Solo si Resend no está disponible
   - Puede no funcionar en Railway (bloqueado)

### Código:

```python
# lib/email.py ahora intenta Resend primero
if RESEND_AVAILABLE_AND_CONFIGURED:
    return _send_email_resend(to, subject, html, text)
elif SMTP_AVAILABLE:
    return _send_email_smtp(to, subject, html, text)  # Fallback
```

---

## ✅ Verificación

### Después de configurar `RESEND_API_KEY` en Railway:

1. Los logs mostrarán:
   ```
   ✅ Resend configurado correctamente
   ```

2. Los emails se enviarán usando Resend:
   ```
   OK: Email enviado exitosamente a usuario@email.com usando Resend: Asunto
       Email ID: abc123...
   ```

3. Si Resend falla, intentará SMTP automáticamente (fallback)

---

## 📊 Plan Gratuito de Resend

- ✅ **3,000 emails/mes** gratis
- ✅ Sin límite de tiempo
- ✅ Suficiente para ~270 clientes activos
- ✅ Cuando crezcas: $20/mes por 50,000 emails

---

## 🎯 Próximos Pasos

1. ✅ Código implementado
2. ⏳ Crear cuenta en Resend
3. ⏳ Obtener API key
4. ⏳ Configurar `RESEND_API_KEY` en Railway
5. ⏳ Probar con un registro nuevo

---

## 🔍 Troubleshooting

### Si ves "Resend no está instalado":
```bash
pip install resend
```

### Si ves "RESEND_API_KEY no está configurado":
- Verifica que la variable esté en Railway
- Verifica que el nombre sea exactamente `RESEND_API_KEY`
- Reinicia el servicio en Railway

### Si Resend falla y usa SMTP:
- Verifica que la API key sea correcta
- Verifica que no haya errores en los logs
- Resend intentará fallback a SMTP automáticamente

---

## 📝 Notas Importantes

1. **Resend es el método principal** - Funciona en Railway
2. **SMTP es fallback** - Solo si Resend no está disponible
3. **No necesitas cambiar código** - Todo está implementado
4. **Solo necesitas configurar la API key** en Railway

¡Listo! Una vez que configures `RESEND_API_KEY` en Railway, los emails funcionarán automáticamente.


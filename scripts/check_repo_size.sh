#!/bin/bash
# Script para verificar el tamaño del repositorio y detectar archivos grandes

echo "📊 Verificando tamaño del repositorio..."

# Tamaño del .git
if [ -d ".git" ]; then
    git_size=$(du -sh .git 2>/dev/null | cut -f1)
    echo "📦 Tamaño de .git: $git_size"
else
    echo "⚠️  No se encontró .git"
fi

# Archivos grandes en el working directory (no ignorados)
echo ""
echo "🔍 Buscando archivos grandes (>10MB) en el working directory..."
find . -type f -size +10M ! -path "./.git/*" ! -path "./venv_ingesta/*" ! -path "./data/*" ! -path "./node_modules/*" ! -path "./.next/*" 2>/dev/null | while read file; do
    size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
    size_mb=$((size / 1048576))
    echo "  ⚠️  $file (${size_mb}MB)"
done

# Verificar si hay archivos rastreados que deberían estar ignorados
echo ""
echo "🔍 Verificando archivos rastreados que deberían estar en .gitignore..."
git ls-files | grep -E "venv_ingesta|data/|\.pdf$|\.epub$|\.pkl$|\.bin$|node_modules/|\.next/" && echo "  ❌ Archivos no deseados encontrados!" || echo "  ✅ No se encontraron archivos no deseados"

echo ""
echo "✅ Verificación completada"















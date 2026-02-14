#!/bin/bash
# init.sh - Iniciar servidor PALABRIA

# Asegurar que estamos en el directorio correcto
cd "$(dirname "$0")"

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "🚀 Iniciando PALABRIA..."
echo "📂 Web: http://127.0.0.1:8000"
echo "📚 Docs: http://127.0.0.1:8000/docs"
echo "-----------------------------------"

# Ejecutar servidor uvicorn
uvicorn backend.main:app --host 127.0.0.1 --port 8000

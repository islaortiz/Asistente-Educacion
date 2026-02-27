#!/bin/bash
set -e

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 Configurando Entorno Educativo AI...${NC}"

# 1. Configuración de Entorno Virtual
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}📦 Creando entorno virtual (.venv)...${NC}"
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Instalación de Dependencias
echo -e "${BLUE}⬇️  Instalando librerías (esto puede tardar)...${NC}"
pip install -q -r requirements.txt
# Verificar si el modelo de spacy está instalado, si no, descargarlo
if ! python -m spacy info es_core_news_lg > /dev/null 2>&1; then
    echo "   -> Descargando modelo de lenguaje SpaCy..."
    python -m spacy download es_core_news_lg
fi

echo ""
echo -e "${GREEN}✅ Entorno configurado correctamente.${NC}"
echo ""
echo "Para iniciar el sistema, por favor abre 2 terminales nuevas en esta carpeta:"
echo ""
echo -e "${BLUE}=== TERMINAL 1 (Backend) ===${NC}"
echo "source .venv/bin/activate"
echo "uvicorn backend.main:app --host 127.0.0.1 --port 8000"
echo ""
echo -e "${BLUE}=== TERMINAL 2 (Frontend) ===${NC}"
echo "source .venv/bin/activate"
echo "export BACKEND_URL='http://127.0.0.1:8000'"
echo "streamlit run frontend/app.py --server.port=8501"
echo ""

# 🎓 PALABRIA: Asistente de Escritura Académica

> Sistema inteligente para la corrección y mejora de textos académicos, potenciado por LLMs locales (Mistral) y RAG.

![Estado](https://img.shields.io/badge/Estado-Beta-blue)
![Tech](https://img.shields.io/badge/Backend-FastAPI-green)
![Tech](https://img.shields.io/badge/Frontend-VanillaJS-yellow)
![AI](https://img.shields.io/badge/AI-Mistral_7B-violet)

## 📋 Descripción

PALABRIA es una plataforma diseñada para ayudar a estudiantes a mejorar su redacción académica. Detecta patrones informales (como el "tú impersonal"), ofrece correcciones estilísticas y permite a los profesores monitorizar el progreso de su clase.

**Características Principales:**
*   **Corrección Inteligente**: Análisis de texto local y privado.
*   **Dashboards por Rol**: Vistas específicas para Alumnos y Profesores.
*   **Historial de Versiones**: Guarda métricas de cada documento analizado.
*   **Interfaz Moderna**: Experiencia de usuario fluida y reactiva.

## 🚀 Guía de Inicio Rápido

### 1. Instalación (Solo la primera vez)
El script `start.sh` se encarga de crear el entorno virtual de Python (`.venv`) e instalar todas las dependencias necesarias.
```bash
bash start.sh
```

### 2. Iniciar la Aplicación (Día a día)
Para levantar el servidor rápidamente, utiliza el script `init.sh`. Este script activa el entorno y lanza el servidor.
```bash
bash init.sh
```

> **Nota**: Si prefieres hacerlo manualmente:
> `source .venv/bin/activate`
> `uvicorn backend.main:app --host 127.0.0.1 --port 8000`

### 3. Detener la Aplicación
Para detener el servidor, simplemente pulsa `CTRL + C` en la terminal.

### 4. Acceso
*   💻 **Web App**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
*   📚 **Documentación API**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## 📂 Estructura del Proyecto

```text
/
├── backend/                # Lógica del servidor y API
│   ├── main.py             # Punto de entrada FastAPI
│   ├── db.py               # Gestión de base de datos SQLite
│   ├── model.py            # Inferencia LLM (Mistral)
│   ├── metrics.py          # Cálculo de métricas de texto
│   └── utils.py            # Procesamiento de PDF/Texto
├── frontend/               # Interfaz de Usuario (Web App)
│   ├── index.html          # Punto de entrada HTML
│   └── static/             # Recursos Estáticos
│       ├── css/
│       │   └── style.css   # Estilos (Glassmorphism, Dark Mode)
│       └── js/
│           └── app.js      # Lógica Frontend (SPA, Gráficos)
├── data/                   # Almacenamiento persistente
│   └── palabria.db         # Base de datos (Usuarios, Métricas)
├── init.sh                 # Script de arranque rápido
├── start.sh                # Script de instalación/setup
└── requirements.txt        # Dependencias Python
```

## 🛠 Desarrollo y Contribución

Consulta el archivo `TODO.md` para ver la hoja de ruta y las tareas pendientes.

**Comandos Útiles:**
*   Verificar estado del servidor: `curl http://127.0.0.1:8000/status/`
*   Reiniciar base de datos (¡Precaución!): Borrar `data/palabria.db`.
*   Poblar la BBDD vectorial del RAG con los pdf: `python -m backend.rag.ingest`
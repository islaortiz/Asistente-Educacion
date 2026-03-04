# PALABRIA | Asistente Educativo Inteligente

**PALABRIA** es una plataforma educativa diseñada para mejorar la calidad de la redacción académica y facilitar el aprendizaje mediante inteligencia artificial. Su enfoque principal es la detección y corrección del "tú impersonal", transformando textos informales en versiones más objetivas y profesionales.

## 🚀 Características Principales

### Para Estudiantes
- **✒️ Corrector de Textos**: Analiza documentos PDF o texto plano para identificar el uso del "tú" impersonal.
- **💡 Feedback Pedagógico**: Genera explicaciones claras sobre por qué se realizaron los cambios, fomentando el aprendizaje.
- **📝 Autoevaluación (RAG)**: Genera cuestionarios basados en los documentos de la base de conocimientos del profesor.
- **📖 Historial**: Seguimiento de documentos analizados y resultados de autoevaluaciones previas.

### Para Profesores
- **📊 Panel de Control**: Visualización de métricas globales del grupo y rendimiento individual de los alumnos.
- **📚 Gestión de Base Vectorial**: Capacidad para subir y gestionar documentos PDF que servirán como contexto para las autoevaluaciones.
- **⚙️ Generación de Preguntas**: Automatización de la creación de preguntas teóricas a partir de los documentos subidos (RAG).

## 🛠️ Tecnologías Utilizadas

- **Frontend**: HTML5, CSS3, JavaScript (Vanilla), Chart.js para visualización de datos.
- **Backend**: Python con [FastAPI](https://fastapi.tiangolo.com/).
- **IA/ML**: 
  - **Mistral 7B Instruct v0.3**: Modelo de lenguaje principal.
  - **Quantización 4-bit (bitsandbytes)**: Optimización para ejecución eficiente.
  - **RAG (Retrieval-Augmented Generation)**: Uso de [ChromaDB](https://www.trychroma.com/) para búsqueda semántica.
- **Base de Datos**: SQLite para persistencia de usuarios, documentos y métricas.


## 📂 Estructura del Proyecto

- `backend/`: Lógica del servidor, API, base de datos y modelos de IA.
- `frontend/`: Interfaz de usuario (HTML, CSS, JS).
- `data/`: Almacenamiento de la base de datos SQLite y archivos vectoriales.
- `requirements.txt`: Dependencias del sistema.

## 📝 Licencia

Este proyecto está bajo la licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.

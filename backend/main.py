# backend/main.py
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import hashlib
import time
import os

import backend.model as model
from backend.metrics import _normalize_for_diff, word_levenshtein_count
from backend.utils import extract_text_from_pdf, split_into_sentences, posible_tu_impersonal
from backend.rag.ingest import (
    delete_indexed_source,
    ingest_pdf_bytes,
    list_indexed_sources,
    extract_pdf_pages,
    retrieve_chunks,
    DEFAULT_INPUT_DIR,
)
from backend.db import (
    init_db, user_exists, create_user, get_user_id, get_user_role,
    record_usage, create_document, insert_metric,
    get_user_overview, get_user_documents, get_document_metrics,
    sanitize_username, delete_document, record_login_ts,
    close_open_session, get_user_weekly_activity, get_global_overview,
    save_rag_questions, get_rag_questions, delete_rag_questions,
    get_quiz_questions, save_quiz_correction, get_user_quiz_corrections
)
import re

app = FastAPI(title="PALABRIA Backend")

# Mount Static Files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_index():
    return FileResponse("frontend/index.html")
    
@app.get("/app")
async def read_app():
    return FileResponse("frontend/index.html")

init_db()


def require_professor_user(username: str) -> int:
    username = sanitize_username(username)
    uid = get_user_id(username)
    if uid is None:
        raise HTTPException(status_code=403, detail="Usuario no valido.")
    if get_user_role(username) != "professor":
        raise HTTPException(status_code=403, detail="Solo el profesor puede gestionar la BBDD vectorial.")
    return uid


@app.get("/status/")
def check_status():
    return {
        "modelo_listo": model.MODEL_LOADED,
        "progress": model.LOAD_PROGRESS,
        "message": model.LOAD_MESSAGE,
    }

@app.post("/load/")
def trigger_load():
    model.ensure_model_loaded(async_load=True)
    return {"ok": True}

@app.post("/users/create")
def user_create(username: str = Form(...), role: str = Form("student")):
    try:
        username = sanitize_username(username)
        if user_exists(username):
            raise HTTPException(status_code=409, detail="El usuario ya existe. Elige otro nombre.")
        
        # Validar rol básico
        if role not in ["student", "professor"]:
            role = "student"
            
        uid = create_user(username, role=role)
        record_usage(uid, "login", None)
        record_login_ts(uid, time.time())
        return {"ok": True, "user_id": uid, "username": username, "role": role}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/users/login")
def user_login(username: str = Form(...)):
    try:
        username = sanitize_username(username)
        uid = get_user_id(username)
        if uid is None:
            raise HTTPException(status_code=404, detail="La cuenta no existe. Crea una nueva.")
            
        role = get_user_role(username)
        record_usage(uid, "login", None)
        record_login_ts(uid, time.time())
        return {"ok": True, "user_id": uid, "username": username, "role": role}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/users/logout")
def user_logout(username: str = Form(...)):
    try:
        username = sanitize_username(username)
        uid = get_user_id(username)
        if uid is None:
            raise HTTPException(status_code=404, detail="Usuario no válido.")
        close_open_session(uid, time.time())
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/users/heartbeat")
def user_heartbeat(username: str = Form(...)):
    try:
        username = sanitize_username(username)
        uid = get_user_id(username)
        if uid is None:
            raise HTTPException(status_code=404, detail="Usuario no válido.")
        now = time.time()
        record_usage(uid, "heartbeat", now)
        close_open_session(uid, now_epoch=now, idle_grace=1800)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/process/")
async def process_pdf(
    file: UploadFile = File(...),
    username: str = Form(...),
):
    username = sanitize_username(username)
    uid = get_user_id(username)
    if uid is None:
        raise HTTPException(status_code=403, detail="Usuario no válido. Inicia sesión con una cuenta existente.")

    content = await file.read()
    original_text = extract_text_from_pdf(content)

    errores_posibles, _ = posible_tu_impersonal(original_text)
    if not isinstance(errores_posibles, list):
        errores_posibles = []

    corrected_text = model.correct_full_text(original_text)
    feedback = model.generate_feedback(original_text, corrected_text)

    sentences = split_into_sentences(original_text)
    total_frases = len(sentences)
    total_errores = len(errores_posibles)
    cambios_modelo_total = word_levenshtein_count(original_text, corrected_text)

    text_hash = hashlib.sha256((original_text or "").encode("utf-8")).hexdigest()
    doc_id = create_document(uid, file.filename, text_hash,
                           original_text=original_text, corrected_text=corrected_text, 
                           feedback=feedback)

    insert_metric(doc_id, "total_frases", float(total_frases))
    insert_metric(doc_id, "frases_con_tu_impersonal", float(total_errores))
    insert_metric(doc_id, "cambios_propuestos_modelo", float(cambios_modelo_total))
    insert_metric(doc_id, "cambios_realizados_usuario", float(cambios_modelo_total))

    record_usage(uid, "pdf_uploaded", None)

    return {
        "doc_id": doc_id,
        "original_text": original_text,
        "corrected": corrected_text,
        "feedback": feedback,
        "errores_posibles": errores_posibles,
        "mensaje_errores": (
            "No se detectaron errores de 'tú' impersonal."
            if not errores_posibles
            else f"Se detectaron {len(errores_posibles)} posibles usos del 'tú' impersonal."
        ),
        "metricas": {
            "total_frases": total_frases,
            "frases_con_tu_impersonal": total_errores,
            "cambios_propuestos_modelo": cambios_modelo_total,
            "cambios_realizados_usuario": cambios_modelo_total,
        },
    }

@app.post("/process_text/")
async def process_text(
    username: str = Form(...),
    text: str = Form(...),
    filename: str = Form(None),
):
    username = sanitize_username(username)
    uid = get_user_id(username)
    if uid is None:
        raise HTTPException(status_code=403, detail="Usuario no válido. Inicia sesión con una cuenta existente.")

    original_text = text or ""

    errores_posibles, _ = posible_tu_impersonal(original_text)
    if not isinstance(errores_posibles, list):
        errores_posibles = []

    corrected_text = model.correct_full_text(original_text)
    feedback = model.generate_feedback(original_text, corrected_text)

    sentences = split_into_sentences(original_text)
    total_frases = len(sentences)
    total_errores = len(errores_posibles)
    cambios_modelo_total = word_levenshtein_count(original_text, corrected_text)

    text_hash = hashlib.sha256((original_text or "").encode("utf-8")).hexdigest()
    doc_id = create_document(uid, filename or "entrada_texto.txt", text_hash, 
                           original_text=original_text, corrected_text=corrected_text, 
                           feedback=feedback)

    insert_metric(doc_id, "total_frases", float(total_frases))
    insert_metric(doc_id, "frases_con_tu_impersonal", float(total_errores))
    insert_metric(doc_id, "cambios_propuestos_modelo", float(cambios_modelo_total))
    insert_metric(doc_id, "cambios_realizados_usuario", float(cambios_modelo_total))

    record_usage(uid, "text_uploaded", None)

    return {
        "doc_id": doc_id,
        "original_text": original_text,
        "corrected": corrected_text,
        "feedback": feedback,
        "errores_posibles": errores_posibles,
        "mensaje_errores": (
            "No se detectaron errores de 'tú' impersonal."
            if not errores_posibles
            else f"Se detectaron {len(errores_posibles)} posibles usos del 'tú' impersonal."
        ),
        "metricas": {
            "total_frases": total_frases,
            "frases_con_tu_impersonal": total_errores,
            "cambios_propuestos_modelo": cambios_modelo_total,
            "cambios_realizados_usuario": cambios_modelo_total,
        },
    }

@app.post("/documents/{doc_id}/metrics")
def add_document_metric(
    doc_id: int,
    name: str = Form(...),
    value: float = Form(...),
):
    try:
        insert_metric(doc_id, name, float(value))
        return {"ok": True, "document_id": doc_id, "metric_name": name, "metric_value": float(value)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/documents/{doc_id}/user_changes")
def update_user_changes(
    doc_id: int,
    changes: int = Form(...),
):
    try:
        insert_metric(doc_id, "cambios_realizados_usuario", float(changes))
        return {"ok": True, "document_id": doc_id, "metric_name": "cambios_realizados_usuario", "metric_value": float(changes)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/users/{username}/overview")
def user_overview(username: str):
    return get_user_overview(username)

@app.get("/users/{username}/documents")
def user_documents(username: str):
    return {"documents": get_user_documents(username)}

@app.get("/documents/{doc_id}")
def get_document(doc_id: int):
    """Obtener detalles completos de un documento"""
    try:
        from backend.db import db
        with db() as con:
            doc = con.execute(
                "SELECT id, user_id, filename, uploaded_at, original_text, corrected_text, feedback FROM documents WHERE id=?",
                (doc_id,)
            ).fetchone()
            
            if not doc:
                raise HTTPException(status_code=404, detail="Documento no encontrado")
            
            metrics = con.execute(
                "SELECT metric_name, metric_value FROM metrics WHERE document_id=?",
                (doc_id,)
            ).fetchall()
            
            metricas = {m["metric_name"]: m["metric_value"] for m in metrics}
            
            return {
                "doc_id": doc["id"],
                "filename": doc["filename"],
                "uploaded_at": doc["uploaded_at"],
                "original_text": doc["original_text"] or "",
                "corrected": doc["corrected_text"] or "",
                "feedback": doc["feedback"] or "",
                "metricas": metricas
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{doc_id}/metrics")
def document_metrics(doc_id: int):
    return {"doc_id": doc_id, "metrics": get_document_metrics(doc_id)}

@app.get("/users/{username}/weekly_activity")
def user_weekly_activity(username: str):
    return {"username": username, "activity": get_user_weekly_activity(username)}


@app.get("/rag/documents")
def rag_list_documents(username: str):
    require_professor_user(username)
    return {"documents": list_indexed_sources()}


@app.post("/rag/documents")
async def rag_upload_document(
    file: UploadFile = File(...),
    username: str = Form(...),
):
    uid = require_professor_user(username)

    file_name = Path(file.filename or "").name
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    content = await file.read()
    try:
        result = ingest_pdf_bytes(
            pdf_bytes=content,
            filename=file_name,
            batch_size=64,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo indexar el PDF: {e}")

    record_usage(uid, "rag_pdf_uploaded", None)
    return {"ok": True, **result}


@app.delete("/rag/documents/{source_name}")
def rag_delete_document(source_name: str, username: str):
    uid = require_professor_user(username)
    try:
        result = delete_indexed_source(source_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo eliminar el PDF: {e}")

    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="Archivo no encontrado en la BBDD vectorial.")

    # Eliminar preguntas asociadas
    delete_rag_questions(source_name)

    record_usage(uid, "rag_pdf_deleted", None)
    return {"ok": True, **result}


@app.post("/rag/documents/{source_name}/questions")
def rag_generate_questions(source_name: str, username: str):
    """Genera 5 preguntas teóricas a partir del PDF indexado."""
    require_professor_user(username)

    # Leer el PDF desde disco
    pdf_path = DEFAULT_INPUT_DIR / source_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF '{source_name}' no encontrado en disco.")

    if not model.MODEL_LOADED:
        raise HTTPException(status_code=503, detail="El modelo LLM aún no está cargado. Espera a que termine de cargar.")

    # Extraer texto del PDF
    pages = extract_pdf_pages(pdf_path)
    full_text = "\n".join(text for _, text in pages)
    if not full_text.strip():
        raise HTTPException(status_code=400, detail="No se pudo extraer texto del PDF.")

    # Generar preguntas con el LLM
    raw_output = model.generate_questions(full_text)
    if not raw_output:
        raise HTTPException(status_code=500, detail="El modelo no generó preguntas.")

    # Parsear preguntas (líneas que empiezan con un número)
    lines = raw_output.strip().split("\n")
    questions = []
    for line in lines:
        line = line.strip()
        if re.match(r'^\d+\.\s+', line):
            # Quitar el número del inicio
            q_text = re.sub(r'^\d+\.\s*', '', line).strip()
            if q_text:
                questions.append(q_text)

    if not questions:
        # Fallback: usar todas las líneas no vacías
        questions = [l.strip() for l in lines if l.strip()]

    # Limitar a 5 preguntas
    questions = questions[:5]

    # Borrar preguntas anteriores y guardar las nuevas
    delete_rag_questions(source_name)
    save_rag_questions(source_name, questions)

    return {"ok": True, "source": source_name, "questions": get_rag_questions(source_name)}


@app.get("/rag/documents/{source_name}/questions")
def rag_get_questions(source_name: str, username: str):
    """Recupera las preguntas guardadas para un PDF."""
    require_professor_user(username)
    questions = get_rag_questions(source_name)
    return {"source": source_name, "questions": questions}


@app.get("/rag/quiz")
def rag_quiz():
    """Devuelve 1 pregunta aleatoria por cada documento RAG (para autoevaluación)."""
    try:
        questions = get_quiz_questions()
        return {"questions": questions}
    except Exception as e:
        # La tabla puede no existir si el servidor no se reinició
        print(f"[WARN] Error en /rag/quiz: {e}")
        return {"questions": []}


@app.post("/rag/quiz/correct")
def rag_quiz_correct(
    question: str = Form(...),
    answer: str = Form(...),
    source_name: str = Form(""),
    username: str = Form(None),
):
    """Corrige una respuesta de autoevaluación usando RAG + LLM."""
    if not answer.strip():
        raise HTTPException(status_code=400, detail="La respuesta está vacía.")

    if not model.MODEL_LOADED:
        raise HTTPException(status_code=503, detail="El modelo LLM aún no está cargado.")

    # 1. Recuperar el chunk más relevante del documento de origen
    context_text = ""
    context_source = source_name or "Documento desconocido"
    context_page = 0
    try:
        chunks = retrieve_chunks(
            query=question,
            source_name=source_name if source_name else None,
            n_results=1,
        )
        if chunks:
            context_text = chunks[0]["text"]
            context_source = chunks[0]["source"]
            context_page = chunks[0]["page"]
    except Exception as e:
        print(f"[WARN] Error en retrieve_chunks: {e}")

    if not context_text:
        raise HTTPException(status_code=404, detail="No se encontró contexto en la base vectorial para esta pregunta.")

    # 2. Generar corrección con el LLM
    raw_output = model.correct_quiz_answer(
        question=question,
        answer=answer,
        context=context_text,
    )

    if not raw_output:
        raise HTTPException(status_code=500, detail="El modelo no generó corrección.")

    # 3. Parsear la respuesta estructurada del LLM
    evaluation = ""
    correction = raw_output
    relevant_context = ""

    # Extraer EVALUACIÓN
    eval_match = re.search(r'EVALUACI[ÓO]N:\s*(.+?)(?=\nCORRECCI[ÓO]N:|\Z)', raw_output, re.DOTALL | re.IGNORECASE)
    if eval_match:
        evaluation = eval_match.group(1).strip()

    # Extraer CORRECCIÓN
    corr_match = re.search(r'CORRECCI[ÓO]N:\s*(.+?)(?=\nCITA RELEVANTE:|\Z)', raw_output, re.DOTALL | re.IGNORECASE)
    if corr_match:
        correction = corr_match.group(1).strip()

    # Extraer CITA RELEVANTE
    cite_match = re.search(r'CITA RELEVANTE:\s*(.+)', raw_output, re.DOTALL | re.IGNORECASE)
    if cite_match:
        relevant_context = cite_match.group(1).strip()

    # Fallback: si no se extrajo cita, usar contexto truncado por frases completas
    if not relevant_context:
        sentences = context_text.split('. ')
        relevant_context = '. '.join(sentences[:3])
        if not relevant_context.endswith('.'):
            relevant_context += '.'

    # Persist correction if username provided
    if username:
        try:
            uname = sanitize_username(username)
            uid = get_user_id(uname)
            if uid is not None:
                # Save to DB (best-effort)
                save_quiz_correction(uid, question, answer, evaluation, correction, context_source, str(context_page))
        except Exception as e:
            print(f"[WARN] No se pudo guardar la corrección de quiz: {e}")

    return {
        "ok": True,
        "evaluation": evaluation,
        "correction": correction,
        "relevant_context": relevant_context,
        "source": context_source,
        "page": context_page,
    }




@app.delete("/documents/{doc_id}")
def delete_doc(doc_id: int):
    ok = delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return {"ok": True, "deleted_id": doc_id}

@app.get("/professor/students/{username}/documents")
def professor_student_documents(username: str):
    """Obtener todos los documentos de un estudiante para el profesor"""
    try:
        username = sanitize_username(username)
        uid = get_user_id(username)
        if uid is None:
            raise HTTPException(status_code=404, detail="Estudiante no encontrado")
        
        from backend.db import db
        with db() as con:
            docs = con.execute(
                """SELECT id, filename, uploaded_at, original_text, corrected_text, feedback 
                   FROM documents WHERE user_id=? ORDER BY uploaded_at DESC""",
                (uid,)
            ).fetchall()
            
            documents = []
            for doc in docs:
                metrics = con.execute(
                    "SELECT metric_name, metric_value FROM metrics WHERE document_id=?",
                    (doc["id"],)
                ).fetchall()
                
                metricas = {m["metric_name"]: m["metric_value"] for m in metrics}
                
                documents.append({
                    "id": doc["id"],
                    "filename": doc["filename"],
                    "uploaded_at": doc["uploaded_at"],
                    "original_text": doc["original_text"] or "",
                    "corrected": doc["corrected_text"] or "",
                    "feedback": doc["feedback"] or "",
                    "metricas": metricas
                })
            
            return {"username": username, "documents": documents}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/student/{username}/corrections")
def student_own_corrections(username: str):
    """Obtener correcciones de autoevaluación (quiz) guardadas por un estudiante."""
    try:
        corrections = get_user_quiz_corrections(username)
        return {"username": username, "corrections": corrections}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/student/{username}/documents")
def student_own_documents(username: str):
    """Obtener todos los documentos propios del estudiante"""
    from backend.db import db  # Local import to prevent circular dependency
    try:
        username = sanitize_username(username)
        uid = get_user_id(username)
        if uid is None:
            raise HTTPException(status_code=404, detail="Estudiante no encontrado")
        
        with db() as con:
            docs = con.execute(
                """SELECT id, filename, uploaded_at, original_text, corrected_text, feedback 
                   FROM documents WHERE user_id=? ORDER BY uploaded_at DESC""",
                (uid,)
            ).fetchall()
            
            documents = []
            for doc in docs:
                metrics = con.execute(
                    "SELECT metric_name, metric_value FROM metrics WHERE document_id=?",
                    (doc["id"],)
                ).fetchall()
                
                metricas = {m["metric_name"]: m["metric_value"] for m in metrics}
                
                documents.append({
                    "id": doc["id"],
                    "filename": doc["filename"],
                    "uploaded_at": doc["uploaded_at"],
                    "original_text": doc["original_text"] or "",
                    "corrected": doc["corrected_text"] or "",
                    "feedback": doc["feedback"] or "",
                    "metricas": metricas
                })
            
            return {"username": username, "documents": documents}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/professor/students/{username}/corrections")
def professor_student_corrections(username: str):
    """Obtener correcciones de autoevaluación (quiz) guardadas por un estudiante."""
    try:
        corrections = get_user_quiz_corrections(username)
        return {"username": username, "corrections": corrections}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/professor/overview")
def professor_overview():
    return get_global_overview()

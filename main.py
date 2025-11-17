import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Project, Task, Note

app = FastAPI(title="Project Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helpers
class PyObjectId(ObjectId):
    @staticmethod
    def __get_validators__():
        yield PyObjectId.validate

    @staticmethod
    def validate(v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")


def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    d = {**doc}
    if d.get("_id"):
        d["_id"] = str(d["_id"])
    # convert datetime to isoformat for timestamps
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# Root endpoints
@app.get("/")
def read_root():
    return {"message": "Project Management Backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "Unknown"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# Projects
@app.get("/api/projects")
def list_projects(status: Optional[str] = None, limit: int = Query(100, le=500)):
    filt = {"status": status} if status else {}
    docs = get_documents("project", filt, limit)
    # attach counts
    for d in docs:
        d["_id"] = str(d["_id"])  # ensure string id
        pid = d["_id"]
        d["task_counts"] = {
            "open": db["task"].count_documents({"project_id": pid, "status": "open"}),
            "in_progress": db["task"].count_documents({"project_id": pid, "status": "in-progress"}),
            "done": db["task"].count_documents({"project_id": pid, "status": "done"}),
        }
        d["notes_count"] = db["note"].count_documents({"project_id": pid})
    return [serialize_doc(x) for x in docs]


@app.post("/api/projects", status_code=201)
def create_project(project: Project):
    inserted_id = create_document("project", project)
    doc = db["project"].find_one({"_id": ObjectId(inserted_id)})
    return serialize_doc(doc)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
    doc = db["project"].find_one({"_id": ObjectId(project_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")
    # attach related counts
    doc = serialize_doc(doc)
    doc["task_counts"] = {
        "open": db["task"].count_documents({"project_id": project_id, "status": "open"}),
        "in_progress": db["task"].count_documents({"project_id": project_id, "status": "in-progress"}),
        "done": db["task"].count_documents({"project_id": project_id, "status": "done"}),
    }
    doc["notes_count"] = db["note"].count_documents({"project_id": project_id})
    return doc


# Tasks
@app.get("/api/tasks")
def list_tasks(project_id: Optional[str] = None, status: Optional[str] = None, limit: int = Query(200, le=1000)):
    filt = {}
    if project_id:
        filt["project_id"] = project_id
    if status:
        filt["status"] = status
    docs = get_documents("task", filt, limit)
    return [serialize_doc(x) for x in docs]


@app.post("/api/tasks", status_code=201)
def create_task(task: Task):
    # validate project exists
    if not ObjectId.is_valid(task.project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not db["project"].find_one({"_id": ObjectId(task.project_id)}):
        raise HTTPException(status_code=404, detail="Project not found")
    inserted_id = create_document("task", task)
    doc = db["task"].find_one({"_id": ObjectId(inserted_id)})
    return serialize_doc(doc)


# Notes
@app.get("/api/notes")
def list_notes(project_id: Optional[str] = None, limit: int = Query(200, le=1000)):
    filt = {"project_id": project_id} if project_id else {}
    docs = get_documents("note", filt, limit)
    return [serialize_doc(x) for x in docs]


@app.post("/api/notes", status_code=201)
def create_note(note: Note):
    # validate project exists
    if not ObjectId.is_valid(note.project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not db["project"].find_one({"_id": ObjectId(note.project_id)}):
        raise HTTPException(status_code=404, detail="Project not found")
    inserted_id = create_document("note", note)
    doc = db["note"].find_one({"_id": ObjectId(inserted_id)})
    return serialize_doc(doc)


# Simple Chatbot over project data
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    related_projects: List[dict] = []


@app.post("/api/chat", response_model=ChatResponse)
def chat_with_projects(payload: ChatRequest):
    q = (payload.message or "").strip().lower()
    if not q:
        return ChatResponse(reply="Ask me anything about your projects, tasks, or notes.")

    # naive keyword search across name, description, tags, notes, task titles
    proj_matches = list(
        db["project"].find({
            "$or": [
                {"name": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
                {"tags": {"$elemMatch": {"$regex": q, "$options": "i"}}},
            ]
        }).limit(10)
    )

    # also look into tasks and notes for matches and collect project_ids
    task_proj_ids = db["task"].distinct("project_id", {"$or": [
        {"title": {"$regex": q, "$options": "i"}},
        {"description": {"$regex": q, "$options": "i"}},
    ]})

    note_proj_ids = db["note"].distinct("project_id", {"content": {"$regex": q, "$options": "i"}})

    extra_proj_ids = set(list(task_proj_ids) + list(note_proj_ids))
    for pid in extra_proj_ids:
        try:
            if ObjectId.is_valid(pid):
                doc = db["project"].find_one({"_id": ObjectId(pid)})
                if doc:
                    proj_matches.append(doc)
        except Exception:
            continue

    # deduplicate
    seen = set()
    unique = []
    for p in proj_matches:
        pid = str(p.get("_id"))
        if pid not in seen:
            seen.add(pid)
            unique.append(p)

    related = []
    for p in unique[:10]:
        sp = serialize_doc(p)
        pid = sp["_id"]
        open_tasks = list(db["task"].find({"project_id": pid, "status": {"$in": ["open", "in-progress"]}}).limit(5))
        sp["open_tasks"] = [serialize_doc(t) for t in open_tasks]
        notes = list(db["note"].find({"project_id": pid}).sort("created_at", -1).limit(3))
        sp["recent_notes"] = [serialize_doc(n) for n in notes]
        related.append(sp)

    if not related:
        return ChatResponse(reply="I couldn't find anything related. Try different keywords like a project name, tag, or status.", related_projects=[])

    # craft a short summary reply
    names = ", ".join([p.get("name", "Unnamed") for p in related[:5]])
    reply = f"I found {len(related)} related project(s): {names}. I included a few open tasks and recent notes for context."
    return ChatResponse(reply=reply, related_projects=related)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

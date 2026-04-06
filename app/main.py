from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.document_routes import router as document_router
from app.api import resume_routes
from app.api.match_routes import router as match_router
from app.api.review_routes import router as review_router
from app.api.search_routes import router as search_router
from app.api.system_routes import router as system_router
from app.api.tender_routes import router as tender_router
from app.database.connection import init_db

app = FastAPI(title="Tender Resume Matching RAG System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(match_router)
app.include_router(review_router)
app.include_router(search_router)
app.include_router(document_router)
app.include_router(system_router)
app.include_router(tender_router)
app.include_router(resume_routes.router)

@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"message": "Tender RAG system running"}

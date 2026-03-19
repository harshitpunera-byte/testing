# Tender Resume Matching RAG System

This repo now runs as a PostgreSQL + pgvector backed Tender/Resume RAG system.

The active runtime path keeps the existing upload and `/match/` APIs, but the storage/query architecture has been upgraded so that:
- uploaded PDFs still live on disk under `uploads/`
- documents, chunks, evidence, normalized resume data, and search projections live in PostgreSQL
- chunk and summary embeddings live in pgvector
- structured recruiter-style search uses SQL first
- fuzzy retrieval uses semantic or hybrid pgvector-backed search

## What Changed

- PostgreSQL is now the recommended database.
- `pgvector` is the primary vector backend.
- resume ingestion now persists:
  - `documents`
  - `document_chunks`
  - `resume_profiles`
  - `resume_skills`
  - `resume_experiences`
  - `resume_projects`
  - `resume_education`
  - `resume_certifications`
  - `field_evidence`
  - `resume_search_index`
- semantic retrieval no longer depends on FAISS in the active path.
- new endpoints were added for DB health and structured/hybrid resume search.

## Requirements

- Python 3.11+
- Node.js 18+
- Docker Desktop or a local PostgreSQL 16 instance
- Ollama running locally for extraction/reasoning

## Local Setup

1. Copy env:

```powershell
Copy-Item .env.example .env
```

2. Start PostgreSQL + pgvector:

```powershell
docker compose up -d postgres
```

3. Install backend deps:

```powershell
python -m pip install -r requirements.txt
```

4. Run migrations:

```powershell
alembic upgrade head
```

5. Run backend:

```powershell
uvicorn app.main:app --reload
```

6. Run frontend:

```powershell
cd tender-ui
npm install
npm run dev
```

## Environment

Default `.env.example`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/tender_rag
EMBEDDING_DIM=384
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_EXTRACTION_MODEL=phi3
OLLAMA_REASONING_MODEL=mistral
MAX_UPLOAD_FILE_SIZE_MB=25
```

## Database Notes

- Startup validates DB connectivity.
- On PostgreSQL, startup also validates `CREATE EXTENSION IF NOT EXISTS vector`.
- SQLite remains minimally usable for development, but full production search behavior is intended for PostgreSQL.

## Main APIs

Existing:
- `POST /resumes/upload`
- `POST /resumes/upload-multiple`
- `POST /tenders/upload`
- `POST /match/`
- `GET /documents/{document_id}/file`
- `POST /system/clear-database`

New:
- `GET /system/health`
- `POST /search/resumes`
- `GET /search/resumes/{document_id}`

## Query Modes

`POST /search/resumes`

Request:

```json
{
  "query": "Find Python developers with 5+ years experience in Pune under 30 days notice",
  "page": 1,
  "page_size": 20
}
```

Supported search behavior:
- structured filter search
- structured ranking search
- semantic search
- hybrid SQL prefilter + semantic rerank

## Smoke Checks

Backend DB smoke check:

```powershell
python scripts/smoke_test_postgres.py
```

Lightweight tests:

```powershell
pytest
```

## Manual Test Flow

1. `GET /system/health`
   Confirm `"ok": true` and `"pgvector_enabled": true`.

2. Upload a tender:

```powershell
curl -X POST http://127.0.0.1:8000/tenders/upload -F "file=@sample_tender.pdf"
```

3. Upload a resume:

```powershell
curl -X POST http://127.0.0.1:8000/resumes/upload -F "file=@sample_resume.pdf"
```

4. Run structured search:

```powershell
curl -X POST http://127.0.0.1:8000/search/resumes -H "Content-Type: application/json" -d "{\"query\":\"Find Python developers with 5+ years experience\"}"
```

5. Run semantic/hybrid search:

```powershell
curl -X POST http://127.0.0.1:8000/search/resumes -H "Content-Type: application/json" -d "{\"query\":\"Find candidates who worked on claims processing and fraud analytics\"}"
```

6. Run matching:

```powershell
curl -X POST http://127.0.0.1:8000/match/ -H "Content-Type: application/json" -d "{\"query\":\"Shortlist the best candidates for this tender\"}"
```

## Inspect Persistence

Useful PostgreSQL checks:

```sql
SELECT id, document_type, processing_status, original_file_name FROM documents ORDER BY id DESC;
SELECT document_id, chunk_index, page_start, page_end FROM document_chunks ORDER BY id DESC LIMIT 20;
SELECT document_id, candidate_name, normalized_title, total_experience_months FROM resume_profiles ORDER BY id DESC;
SELECT resume_profile_id, skill_name_normalized FROM resume_skills ORDER BY id DESC LIMIT 20;
SELECT document_id, field_name, page_no, confidence FROM field_evidence ORDER BY id DESC LIMIT 20;
SELECT resume_profile_id, candidate_name, skills_normalized FROM resume_search_index ORDER BY id DESC LIMIT 20;
```

## Known Limitations

- legacy FAISS artifacts may still exist on disk, but they are no longer the primary retrieval backend
- SQLite fallback is best-effort and not the target production mode
- resume normalization is intentionally conservative and fills relational tables from current extractor output plus deterministic heuristics
- tender normalization remains lighter than resume normalization

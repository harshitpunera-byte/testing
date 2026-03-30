# Tender RAG System: Detailed Workflow Guide

## 1. Reality Check Before You Read the Code

This repository has evolved beyond the older FAISS-only MVP description.

The active runtime path today is:

- FastAPI backend
- React frontend
- PostgreSQL for primary persistence
- `pgvector` for vector storage in PostgreSQL
- local disk storage for uploaded PDFs
- Ollama for LLM extraction and reasoning

Important mismatches between older docs and current code:

- The active vector path is PostgreSQL + `pgvector`, not FAISS-only.
- The `vector_store/` folder still exists, but it is now mostly legacy cleanup surface.
- Gemini is not implemented in the current code path.
- `LLM_PROVIDER` and `USE_OLLAMA` are present in `.env`, but the current provider code only uses Ollama-specific settings.

## 2. Big Picture Architecture

The real runtime flow is:

1. User uploads tender/resume PDFs from the React UI.
2. FastAPI receives multipart upload requests.
3. Backend validates file type, file size, and PDF readability.
4. Backend computes SHA256 hash for deduplication.
5. File is saved to `uploads/tenders/` or `uploads/resumes/`.
6. A `documents` row is created in PostgreSQL.
7. PDF text is extracted page-by-page using multiple fallbacks.
8. Page text is cleaned.
9. Pages are grouped into semantic blocks.
10. Semantic blocks are chunked.
11. Each chunk is embedded.
12. Chunks and embeddings are persisted to `document_chunks`.
13. Structured data is extracted from the full document text.
14. Evidence snippets are mapped back to the best chunks.
15. Review confidence is computed; low-confidence documents enter a human review queue.
16. Resume documents are normalized into relational recruiter/search tables.
17. User can query the system for:
   - tender QA
   - resume QA
   - combined tender + resume QA
   - tender/resume comparison
   - tender-to-resume matching
   - recruiter-style resume search

## 3. Entry Points

### Backend startup

`app/main.py`

- creates the FastAPI app
- enables CORS for:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`
- mounts routers:
  - `/match`
  - `/reviews`
  - `/search`
  - `/documents`
  - `/system`
  - `/tenders`
  - `/resumes`
- calls `init_db()` on startup

### Frontend entry

`tender-ui/src/App.jsx`

The UI has four practical areas:

- resume upload
- tender upload
- ask AI
- review / structured output workspace

The frontend stores the currently active tender document ID and active resume document IDs, then sends them back to the backend with each query so answers can be restricted to the currently uploaded files.

## 4. Upload APIs

### Tender upload

`POST /tenders/upload`

Route:

- `app/api/tender_routes.py`

Service:

- `app/services/tender_service.py`

This is only a thin wrapper around the shared ingestion pipeline:

- `process_uploaded_document(file, document_type="tender")`

### Resume upload

Routes:

- `POST /resumes/upload`
- `POST /resumes/upload-multiple`

Files:

- `app/api/resume_routes.py`
- `app/services/resume_service.py`

Single and bulk resume upload both use the same ingestion pipeline.

## 5. Shared Document Ingestion Pipeline

Main file:

- `app/services/document_ingestion.py`

Core function:

- `process_uploaded_document()`

This is the most important file in the project for understanding the full data path.

### 5.1 Step A: Validate the upload

Validation happens in:

- `app/utils/file_validator.py`

Checks:

- filename must exist
- extension must end in `.pdf`
- file must not be empty
- file size must be below `MAX_UPLOAD_FILE_SIZE_MB`
- content type must be one of:
  - `application/pdf`
  - `application/octet-stream`
  - empty string
- file bytes must start with `%PDF`
- if PyMuPDF is installed, it attempts to open the PDF and confirm page count > 0

### 5.2 Step B: Compute SHA256 hash

Hashing happens in:

- `app/utils/file_hash.py`

Purpose:

- detect duplicate uploads
- deduplicate by `(document_type, file_hash)` in the `documents` table

### 5.3 Step C: Reuse existing processed document when possible

The code checks whether a document with the same hash already exists and whether its ingestion `pipeline_version` matches:

- `INGESTION_PIPELINE_VERSION = "2026-03-26-exact-facts-v1"`

If yes:

- the previous parsed data is reused
- stored chunks are reused
- the uploaded filename can be updated for display
- the API returns status `duplicate`

This is smarter than naive deduplication because it only reuses old data when the current ingestion version matches.

### 5.4 Step D: Save the file to disk

File storage helpers:

- `app/utils/file_storage.py`

Behavior:

- filename is sanitized
- a timestamp prefix is added
- file bytes are saved under:
  - `uploads/tenders/`
  - `uploads/resumes/`

### 5.5 Step E: Create a `documents` row

Document persistence is handled by:

- `app/services/document_repository.py`

The `documents` table stores:

- document type
- stored filename
- original filename
- SHA256 hash
- disk path
- file size
- MIME type
- processing status
- extraction backend used
- raw text
- markdown text
- structured JSON
- reviewed JSON
- evidence JSON
- review flags
- metadata JSON

## 6. PDF Text Extraction

Main file:

- `app/rag/loader.py`

The extraction output is page-aware:

- `ExtractedDocument`
- list of `PageText(page, text)`

### 6.1 Actual extraction order

The current code path is more nuanced than older docs.

It tries:

1. PyMuPDF family
   - first `pymupdf4llm`
   - then plain PyMuPDF
2. `pdfplumber`
3. `docling`
4. OCR using:
   - PyMuPDF rasterization
   - PIL image conversion
   - Tesseract OCR

### 6.2 Meaningful-text gating

The loader does not blindly accept the first extractor result.

It checks whether the extracted text is meaningful by looking at:

- total extracted character count
- number of meaningful pages
- token density after removing picture/omitted-style noise

That means:

- bad extraction output can be rejected
- the system can continue to a fallback extractor

### 6.3 Page preservation

Unlike the older MVP description, the current implementation is page-aware.

Every page is kept as:

- `page`
- `text`

That later enables:

- chunk page ranges
- evidence page references
- exact-fact extraction on page chunks

## 7. Cleaning

Main file:

- `app/rag/cleaner.py`

Cleaning is still light, but stronger than plain whitespace normalization.

It:

- normalizes whitespace
- removes repeated headers
- removes repeated footers
- removes page-number-only lines like:
  - `Page 4`
  - `4`

This cleaner operates on pages, not on one flat string.

## 8. Semantic Structuring and Chunking

Files:

- `app/rag/semantic_structurer.py`
- `app/rag/chunker.py`

### 8.1 Semantic block building

Before chunking, pages are grouped into semantic blocks using simple heading heuristics.

For tenders, possible sections include:

- eligibility
- qualifications
- experience
- responsibilities
- personnel
- commercial

For resumes, possible sections include:

- summary
- skills
- experience
- projects
- education
- certifications

The structurer scans lines and tries to detect section headers. It then creates blocks with:

- section name
- page_start
- page_end
- text

### 8.2 Chunking strategy

Chunking uses LangChain’s `RecursiveCharacterTextSplitter.from_tiktoken_encoder`.

Configured values:

- `chunk_size = 800`
- `overlap = 150`

These values are defined in:

- `app/services/document_ingestion.py`
- `app/rag/chunker.py`

Important nuance:

- older docs describe these as “words”
- the actual chunk splitter is token-aware through `tiktoken` sizing

### 8.3 Chunk metadata

Each chunk record includes:

- filename
- text
- chunk_id
- document_id
- document_type
- section
- page_start
- page_end
- token_count
- embedding_backend
- chunk_type

## 9. Embeddings

Main file:

- `app/rag/embeddings.py`

### 9.1 Embedding model

Hardcoded model:

- `BAAI/bge-small-en`

Embedding dimension:

- `384`

Dimension is also enforced by:

- env `EMBEDDING_DIM`
- DB vector column size

### 9.2 Loading behavior

The model is loaded with:

- `local_files_only=True`

So the model must already exist locally.

### 9.3 Fallback behavior

If the transformer model is unavailable, the code falls back to a deterministic SHA256 token-hash embedding.

This fallback:

- keeps the pipeline running
- preserves consistent dimensionality
- is much worse semantically than real embeddings

The code logs a critical warning when this happens.

## 10. Vector Storage: What Is Really Happening

This is one of the most important parts to understand.

### 10.1 The legacy-looking part

You will still see:

- `vector_store/`
- names like `search_tender_vectors()`
- names like `search_resume_vectors()`
- `store_document_chunks()`

This makes the project look FAISS-based.

### 10.2 The actual active path

The active vector backend is PostgreSQL + `pgvector`.

Real persistence happens in:

- `app/services/document_repository.py`
- `replace_document_chunks()`

That function writes each chunk into the `document_chunks` table, including its embedding vector.

Resume-level semantic search also uses:

- `resume_search_index.summary_embedding`

### 10.3 Important nuance: `store_document_chunks()` is effectively a no-op

In `app/rag/vector_store.py`, `store_document_chunks()` currently only counts non-empty chunks and returns the count.

It does not write vectors to FAISS.

So the real storage is:

- `replace_document_chunks()` into PostgreSQL

### 10.4 Retrieval modes

`app/rag/vector_store.py` supports:

- semantic chunk search
- hybrid chunk search
- resume-profile semantic search

If PostgreSQL + pgvector is active:

- it runs `cosine_distance` queries in SQL

If PostgreSQL is unavailable:

- it falls back to in-memory cosine comparisons over embeddings loaded from stored chunk rows

### 10.5 Hybrid search

Hybrid retrieval combines:

- semantic rank
- keyword overlap rank

Fusion method:

- reciprocal rank fusion
- `RRF_K = 60`

## 11. Structured Extraction

Files:

- `app/extraction/tender_extractor.py`
- `app/extraction/resume_extractor.py`
- `app/llm/tender_llm_extractor.py`
- `app/llm/resume_llm_extractor.py`
- `app/llm/schemas.py`

### 11.1 Extraction philosophy

Both tender and resume extraction use:

1. heuristic extraction
2. LLM extraction
3. merge heuristic-first, LLM-second

That means:

- if heuristics find a field, the heuristic value is preferred
- LLM fills gaps

### 11.2 Tender fields

Tender structured data contains:

- `role`
- `domain`
- `skills_required`
- `preferred_skills`
- `experience_required`
- `qualifications`
- `responsibilities`

### 11.3 Resume fields

Resume structured data contains:

- `candidate_name`
- `role`
- `domain`
- `skills`
- `experience`
- `qualifications`
- `projects`

Note:

- the final merged resume dict uses `experience`
- the LLM schema uses `experience_years`

### 11.4 LLM extraction prompting

The LLM extractor:

- asks for strict JSON matching a Pydantic-generated JSON schema
- sets temperature to 0
- retries across configured models
- falls back to schema-shaped empty JSON if Ollama fails

## 12. LLM Provider Layer

Main file:

- `app/llm/provider.py`

### 12.1 What is actually implemented

Implemented today:

- Ollama only

Not implemented today:

- Gemini

### 12.2 Model split

The provider supports separate models for:

- general/default
- extraction
- reasoning
- fallback

### 12.3 Ollama call styles

There are two call types:

- `llm_json_extract()` for extraction
- `llm_text_answer()` for QA/reasoning

JSON extraction uses:

- schema-constrained output
- retries
- fallback JSON on failure

Text answering uses:

- grounded prompt
- no-schema free-text answer
- empty string fallback on failure

### 12.4 Backoff behavior

When Ollama errors repeatedly, the provider temporarily backs off instead of hammering the service.

## 13. Evidence Mapping

Main file:

- `app/services/evidence_service.py`

After structured extraction, the system tries to find the best chunk supporting each field.

It stores evidence like:

- source snippet
- page number
- section
- confidence
- character offsets

This evidence is stored both:

- in document JSON (`evidence_map_json`)
- in relational table `field_evidence`

## 14. Review and Human-in-the-Loop Layer

Main file:

- `app/services/review_service.py`

This is a big layer added after the original MVP.

### 14.1 Review thresholds

Current thresholds:

- tender auto-approval threshold: `0.80`
- resume auto-approval threshold: `0.80`

### 14.2 What review does

The system computes field-level and overall confidence, then decides:

- auto approve
- or send to review queue

When review is required:

- `documents.review_status = needs_review`
- a `review_tasks` row is created
- `review_items` rows are created per field
- canonical reviewed data is not yet ready

When auto-approved:

- `documents.review_status = approved`
- `auto_approved = true`
- `canonical_data_ready = true`
- `reviewed_data_json = structured_data_json`

### 14.3 Human review UI

Frontend components:

- `ReviewQueue.jsx`
- `ReviewDetail.jsx`
- `HumanInterventionModal.jsx`

These let a reviewer:

- inspect extracted fields
- see evidence
- edit corrected values
- approve
- reject
- record audit changes

### 14.4 Why this matters downstream

Many downstream services use:

- canonical reviewed data if available
- otherwise raw extracted data

That prevents bad extraction from permanently contaminating matching/search after review corrections are made.

## 15. Resume Normalization Layer

Main file:

- `app/services/profile_normalizer.py`

This is another major post-MVP addition.

The raw resume extraction is normalized into recruiter-friendly relational tables:

- `resume_profiles`
- `resume_skills`
- `resume_experiences`
- `resume_projects`
- `resume_education`
- `resume_certifications`
- `resume_search_index`

The normalizer also heuristically extracts:

- email
- phone
- notice period
- current CTC
- expected CTC
- location
- current company

It builds a summary string and embeds that summary into:

- `resume_search_index.summary_embedding`

This is what enables profile-level semantic search.

## 16. Search Flow

Main file:

- `app/services/search_service.py`

API:

- `POST /search/resumes`

### 16.1 Query parsing

The system extracts structured constraints such as:

- skills
- title
- location
- min experience
- max notice period

### 16.2 Search modes

It classifies a query into one of:

- `structured_filter`
- `structured_rank`
- `semantic`
- `hybrid`

### 16.3 How each mode works

`structured_filter`

- SQL filtering over normalized profile tables

`structured_rank`

- SQL filtering plus a weighted ranking score

`semantic`

- semantic search over `resume_search_index.summary_embedding`

`hybrid`

- structured SQL + semantic rerank

### 16.4 Search scoring

For ranked modes, the current weights are:

- skill score: 55
- experience score: 20
- title score: 10
- semantic score: 15

If pure hybrid rerank is used without title/skill constraints:

- semantic bonus up to 25 is added later

## 17. Matching Flow

Main files:

- `app/api/match_routes.py`
- `app/services/query_service.py`
- `app/services/matching_service.py`

Important architecture point:

- `/match/` does not directly mean “matching only”
- it is the unified query endpoint

`/match/` first calls:

- `answer_query()`

That function decides whether the user’s question is:

- matching
- QA
- no-op

### 17.1 Intent classification

File:

- `app/agents/query_agent.py`

The router looks at:

- the query text
- whether tender documents exist
- whether resume documents exist

If matching keywords are found and both tender + resumes are present:

- it routes to matching mode

Otherwise it routes to QA on:

- tender only
- resume only
- both

## 18. Matching Pipeline in Detail

Main function:

- `match_resumes_with_uploaded_tender()`

### 18.1 Tender selection

If active document IDs are supplied from the UI:

- it uses those exact uploads

Otherwise:

- it can search for a tender using vector retrieval
- or fall back to the latest tender

### 18.2 Tender structured data

It tries to use:

- canonical reviewed tender data first
- then stored structured data
- then fresh extraction from chunks if needed

### 18.3 Resume search query generation

The code builds a better resume search query from tender data using:

- tender role
- tender domain
- required skills
- preferred skills
- required experience

This is important:

- matching is not just “user query -> resume search”
- it is “user query -> extract tender requirements -> build better resume query -> search resumes”

### 18.4 Resume candidate set

If active resume IDs are supplied:

- those resumes become the candidate pool directly

Otherwise:

- it first uses `search_resumes()`
- if that returns nothing, it falls back to chunk-level resume vector search

### 18.5 Resume structured data

For each candidate resume:

- use canonical reviewed data if available
- else use stored extracted data
- else re-extract from chunks

The code also repairs bad resume identity fields like:

- candidate name
- role

using `resume_name_service.py`

### 18.6 Matching score

Current deterministic weights:

- required skills: up to 70
- preferred skills: up to 10
- role match: 10
- domain match: 10
- experience match: 10

Final score is capped at 100.

Verdicts:

- `Highly Suitable`
- `Partially Suitable`
- `Low Suitable`

### 18.7 Cross-document intent safety check

This is one of the smartest parts of the system.

File:

- `app/services/document_intent.py`

The system compares tender intent and resume intent to detect bad semantic matches, for example:

- tender is bidder/company procurement
- resume is an individual consultant CV

If the comparison says this is not a valid match:

- role match is forced false
- experience match is forced false
- final score becomes `0.0`

This is the project’s “cross” or cross-document sanity layer.

### 18.8 Reasoning summary

After deterministic matching, results are passed into a tiny LangGraph graph:

- `app/graph/matching_graph.py`
- `app/agents/reasoning_agent.py`

This layer adds:

- candidate reasoning text
- shortlist summary
- low-suitability summary

The graph is simple:

- one reasoning node
- start -> reasoning -> end

## 19. QA Flow

Main function:

- `_answer_qa()` in `app/services/query_service.py`

### 19.1 Scope resolution

The system answers questions against:

- tender only
- resume only
- both

It prefers active uploads from the UI when provided.

### 19.2 Retrieval for QA

It gathers:

- structured context from canonical structured data
- chunk context from hybrid search over relevant documents

The system uses multiple query variants to improve retrieval.

### 19.3 Exact fact extraction path

Before using an LLM, the system tries deterministic extraction for certain known question types:

- LOA clause
- project cost
- chainage range
- net worth
- DOB

This path is implemented in:

- `_build_exact_fact_answer()`

This is a strong “deterministic before LLM” design choice.

### 19.4 Tender vs resume comparison QA path

If the user asks a comparison-style question, the system can generate a direct tender-vs-resume comparison answer using:

- document intent classification
- mismatches
- similarities
- confusion reasons
- verdict

This is separate from normal answer generation.

### 19.5 LLM QA fallback

If the question is not a deterministic exact-fact case and not a comparison case:

- the system builds a grounded prompt
- includes structured context + evidence chunks
- asks Ollama for a text answer

If Ollama fails:

- it falls back to a simple text summary of the most relevant chunks

## 20. Data Storage Layout

### 20.1 Disk

Uploaded files live on disk:

- `uploads/tenders/`
- `uploads/resumes/`

### 20.2 PostgreSQL tables

Main tables:

- `documents`
- `document_chunks`
- `resume_profiles`
- `resume_skills`
- `resume_experiences`
- `resume_projects`
- `resume_education`
- `resume_certifications`
- `field_evidence`
- `review_tasks`
- `review_items`
- `match_feedback`
- `field_change_audit`
- `resume_search_index`

### 20.3 Legacy vector folder

`vector_store/` still exists, and system cleanup still removes it, but active runtime vectors are not primarily stored there anymore.

## 21. Configs and Defaults

## 21.1 Environment variables in `.env`

Current `.env` values in this repo are effectively:

- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=tender_rag`
- `POSTGRES_USER=postgres`
- `POSTGRES_PASSWORD=<set>`
- `LLM_PROVIDER=ollama`
- `USE_OLLAMA=true`
- `OLLAMA_MODEL=llama3.2`
- `OLLAMA_EXTRACTION_MODEL=phi3`
- `OLLAMA_REASONING_MODEL=mistral`
- `OLLAMA_FALLBACK_MODEL=llama3.2`
- `OLLAMA_BASE_URL=http://localhost:11434`
- `OLLAMA_TIMEOUT_SECONDS=90`
- `DATABASE_URL=postgresql+psycopg2://postgres:...@localhost:5432/tender_rag`
- `EMBEDDING_DIM=384`
- `MAX_UPLOAD_FILE_SIZE_MB=25`

## 21.2 Env vars that are actually used at runtime

Used by backend runtime:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `RUN_ALEMBIC_MIGRATIONS_ON_STARTUP`
- `ALLOW_SQLITE_FALLBACK`
- `EMBEDDING_DIM`
- `MAX_UPLOAD_FILE_SIZE_MB`
- `OLLAMA_MODEL`
- `OLLAMA_EXTRACTION_MODEL`
- `OLLAMA_REASONING_MODEL`
- `OLLAMA_FALLBACK_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_TIMEOUT_SECONDS`

Used by scripts:

- `POSTGRES_SKIP_CREATE_DB`
- `POSTGRES_ADMIN_DB`

Used by frontend:

- `VITE_API_BASE_URL`

## 21.3 Env vars present but not actually used in runtime logic

Currently present but not meaningfully consumed by the main backend logic:

- `LLM_PROVIDER`
- `USE_OLLAMA`

The provider code directly uses Ollama without branching on those flags.

## 21.4 Hardcoded runtime configs

These are not env-driven today:

- embedding model: `BAAI/bge-small-en`
- review threshold: `0.80`
- chunk size: `800`
- chunk overlap: `150`
- hybrid fusion `RRF_K = 60`
- frontend local backend default:
  - `http://127.0.0.1:8000`
- CORS origins:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`

## 21.5 Database behavior configs

`app/database/connection.py` controls:

- whether `DATABASE_URL` wins over individual Postgres vars
- SQLite fallback behavior
- optional auto-migration on startup
- pgvector extension validation
- creation of IVFFlat and GIN indexes

## 21.6 Docker / infra

`docker-compose.yml` defines a local `pgvector/pgvector:pg16` service with:

- default DB `tender_rag`
- default user `postgres`
- default port `5432`

## 22. Frontend Behavior

### Upload flow

Frontend files:

- `TenderUpload.jsx`
- `ResumeUpload.jsx`

What the frontend shows after upload:

- message
- status
- chunks count
- stored chunk count
- review status
- extraction confidence
- review task ID
- extraction backend

### Ask AI flow

Frontend file:

- `AskAgent.jsx`

The UI always calls:

- `POST /match/`

with:

- `query`
- `tender_document_id`
- `resume_document_ids`
- `restrict_to_active_uploads=true`

So the same endpoint is reused for:

- QA
- matching

### Human intervention flow

If a query result says:

- `human_intervention_required = true`

the UI opens a modal and routes the user to the review queue.

## 23. What Is Placeholder vs Active

Clearly active:

- upload flow
- page-aware extraction
- cleaning
- chunking
- embeddings
- pgvector-backed chunk storage
- structured extraction
- evidence mapping
- review queue
- resume normalization
- recruiter search
- QA
- matching
- cross-document comparison

Mostly placeholder or minimal:

- `app/agents/tender_agent.py`
- `app/agents/resume_agent.py`
- `app/agents/scoring_agent.py`
- `app/llm/extractor.py`

Legacy-looking but not primary anymore:

- `vector_store/`
- old FAISS references in older docs

## 24. Mental Model to Keep

If you want one short mental model, use this:

- uploads are stored on disk
- document metadata, chunks, vectors, evidence, review state, and resume search projections live in PostgreSQL
- extraction is deterministic-first and LLM-assisted
- QA tries exact extraction before LLM generation
- matching is tender-guided, deterministic-scored, and protected by cross-document intent checks
- human review upgrades raw extraction into canonical trusted data

## 25. Best Files to Read First

If you want to learn the project in the fastest order, read:

1. `app/services/document_ingestion.py`
2. `app/rag/loader.py`
3. `app/rag/chunker.py`
4. `app/rag/vector_store.py`
5. `app/extraction/tender_extractor.py`
6. `app/extraction/resume_extractor.py`
7. `app/services/profile_normalizer.py`
8. `app/services/review_service.py`
9. `app/services/query_service.py`
10. `app/services/matching_service.py`
11. `tender-ui/src/App.jsx`
12. `tender-ui/src/components/AskAgent.jsx`

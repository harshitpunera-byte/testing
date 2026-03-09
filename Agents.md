# AGENTS.md

AI Development Guide – Tender Resume Matching RAG System

---

# 1. Project Overview

This project builds an **AI-powered Tender Intelligence and Resume Matching system**.

The system processes:

1. Tender documents (RFP PDFs)
2. Resume documents (PDF)

It enables the system to:

• Extract tender requirements
• Store resume knowledge
• Match resumes to tender requirements
• Rank candidates using semantic search

The system uses **Retrieval Augmented Generation (RAG)**.

The final result is a **ranked list of candidates suitable for a tender project**.

---

# 2. Core Business Goal

The system helps companies:

• analyze tender requirements
• find suitable manpower from resume database
• automatically shortlist candidates

Example:

Tender requires:

Education: BTECH Civil
Experience: 5 years
Skill: Highway Construction

System returns:

1. Rahul Sharma – 92% match
2. Ankit Singh – 88% match
3. Ravi Kumar – 81% match

---

# 3. System Architecture

Pipeline:

User Upload → Document Processing → Embeddings → Vector Search → LLM Reasoning → Ranked Results

Detailed flow:

1. Upload tender PDF
2. Upload multiple resumes
3. Extract text from documents
4. Clean text
5. Chunk documents
6. Create embeddings
7. Store embeddings in vector database
8. Retrieve relevant resume chunks
9. Send retrieved context to LLM
10. LLM performs reasoning and ranking
11. Return matched candidates

---

# 4. Technology Stack

Backend: FastAPI
PDF Processing: PyMuPDF
Embeddings: sentence-transformers (BAAI/bge-small-en)
Vector Database: FAISS
LLM: Gemini / OpenAI
Database: PostgreSQL
Frontend: Next.js

---

# 5. Project Folder Structure

tender-rag-system

app/
main.py

```
api/
    tender_routes.py
    resume_routes.py

services/
    tender_service.py
    resume_service.py
    matching_service.py

rag/
    loader.py
    cleaner.py
    chunker.py
    embeddings.py
    vector_store.py
    retriever.py

llm/
    extractor.py

models/
    db_models.py

database/
    connection.py

utils/
    file_storage.py
```

uploads/
tenders/
resumes/

vector_store/

requirements.txt

README.md

---

# 6. Document Processing Pipeline

Every document follows this pipeline:

PDF
→ text extraction
→ cleaning
→ chunking
→ embeddings
→ vector storage

Steps:

1. Load PDF
2. Extract text from each page
3. Clean extracted text
4. Split text into chunks
5. Generate embeddings for each chunk
6. Store embeddings in FAISS

---

# 7. Tender Processing

Tender pipeline:

Upload Tender
→ extract text
→ chunk document
→ embed chunks
→ store vectors

Then LLM extracts structured requirements:

Example output:

{
"education_required": "BTECH Civil",
"experience_required": 5,
"skills_required": ["highway construction"]
}

Store structured data in PostgreSQL.

---

# 8. Resume Processing

Resume pipeline:

Upload Resume
→ extract text
→ clean text
→ chunk resume
→ create embeddings
→ store embeddings

Each chunk must include metadata:

resume_id
candidate_name
file_path

---

# 9. Retrieval Pipeline

When matching resumes:

1. Read tender requirements
2. Convert requirement to query
3. Create embedding for query
4. Search vector database
5. Retrieve top K resume chunks
6. Collect candidate metadata

---

# 10. LLM Reasoning Step

LLM receives:

• tender requirements
• retrieved resume sections

Prompt example:

"From the following resumes identify candidates who match:

Education: BTECH Civil
Experience: 5 years
Skill: Highway construction"

LLM returns ranked candidates.

---

# 11. Matching Score Logic

Score should combine:

Education match
Experience match
Skill similarity
Semantic similarity

Example scoring formula:

final_score =
0.4 * education_match

* 0.3 * experience_match
* 0.3 * semantic_similarity

---

# 12. API Endpoints

Upload Resume

POST /api/resumes/upload

Upload Tender

POST /api/tenders/upload

Get Matches

GET /api/tenders/{tender_id}/matches

---

# 13. Coding Rules for AI Agents

Agents must follow these rules:

• Do not modify core RAG pipeline without approval
• Keep business logic inside services layer
• Keep API routes thin
• Avoid writing large logic inside controllers
• Maintain modular design

---

# 14. Code Quality Rules

Agents must ensure:

• functions remain small
• code is modular
• no duplicated logic
• strong typing where possible
• clean separation of layers

---

# 15. Performance Rules

System must support:

1000+ resumes
500+ page tenders

Optimization rules:

• avoid recomputing embeddings
• store embeddings once
• use batch processing
• limit retrieved chunks

---

# 16. Cost Control Rules

LLM calls must be minimized.

Use LLM only for:

• requirement extraction
• final reasoning

Do not use LLM for:

• filtering resumes
• simple queries

---

# 17. Security Rules

Agents must ensure:

• file upload validation
• size limits on PDFs
• sanitize inputs
• protect database queries

---

# 18. Error Handling

System must gracefully handle:

• corrupted PDFs
• missing text
• empty resumes
• vector search errors

---

# 19. Logging

Log these events:

• document upload
• embedding generation
• vector search queries
• LLM responses

---

# 20. Future Expansion

Possible extensions:

• resume ranking improvements
• tender compliance sheet generation
• candidate scoring dashboard
• enterprise hiring integrations

---

# 21. Current Implementation Progress (Updated March 9, 2026)

Completed:

• FastAPI app bootstrap is implemented in `app/main.py` with root health response.
• Resume upload route is active at `POST /resumes/upload`.
• Tender upload route is active at `POST /tenders/upload`.
• `resume_service.process_resume()` is wired to the RAG pipeline:
  load PDF → clean text → split text → create embedding → store vector.
• `tender_service.process_tender()` base handler is implemented.
• RAG utilities implemented:
  `loader.py`, `cleaner.py`, `chunker.py`, `embeddings.py`, `vector_store.py`.
• Vector search helper `search_vectors()` is implemented in `vector_store.py`.
• File save helper `save_file()` is implemented in `utils/file_storage.py`.
• Installed runtime packages include:
  `fastapi`, `uvicorn`, `python-multipart`, `pymupdf`, `faiss-cpu`, `numpy`.

Pending / In Progress:

• `sentence-transformers` full runtime setup may still require completing `torch` installation.
• Persistence to disk is not yet implemented for:
  `vector_store/resume_index.faiss`
  `vector_store/resume_metadata.json`
• Metadata mapping and retriever integration are still pending.
• API docs in Section 12 should be updated to fully match currently active route prefixes.

---

# End of AGENTS.md

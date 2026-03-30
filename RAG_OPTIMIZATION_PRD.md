# 🏗️ RAG System Optimization: Production Handover PRD

## 1. Objective
Transform a basic RAG system into a production-grade pipeline capable of high-precision synthesis from disparate sources (**Tenders** and **Resumes**) simultaneously, without context starvation or data-mixing hallucinations.

---

## 2. Solved Problems (The "Critical Bug" Audit)

### 🔴 Problem A: Context Starvation (Truncation)
- **Symptom**: AI could find Tender data (Section 1) but kept saying "Resume data (Section 2) not found."
- **Root Cause**: Chunks were appended sequentially. If the Tender search returned 20 chunks, the Resume chunks were at index 21+ and were being cut off by the LLM context window limit.
- **Solution**: Implemented **Interleaved Merging (`1 Tender, 1 Resume, 1 Tender...`)**. This ensures both folders are always present in the AI's "Eyes."

### 🔴 Problem B: The "Short-Word" Search Bug
- **Symptom**: AI could find "Project Cost" but kept failing to find "LOA definition" or "DOB."
- **Root Cause**: A logic filter `len(w) > 3` was removing strings like **"LOA"**, **"DOB"**, **"Net"**, and **"Cost"** from the search query.
- **Solution**: Updated query decomposition to prioritize `TENDER_HINTS` and `RESUME_HINTS` regardless of word length.

### 🔴 Problem C: Prompt Rot (Mutation)
- **Symptom**: Retrieval accuracy degraded the more questions were asked in a session.
- **Root Cause**: The system was prefixing `[RESUME SOURCE]:` to chunks in-place, causing headers to "stack" (e.g., `[RESUME SOURCE]: [RESUME SOURCE]: Text...`) and confusing the LLM.
- **Solution**: Switched to **Dictionary Copying (`dict(chunk)`)** to ensure every query starts with a clean, labeled context.

### 🔴 Problem D: Identity Offset (Resume Page 1 Bias)
- **Symptom**: AI found project experience but missed "Personal Details" (DOB) at the end or top of CVs.
- **Root Cause**: Semantic search prioritized "keyword-heavy" project pages over "metadata-heavy" identity pages.
- **Solution**: Implemented **Identity Prioritization**. The first 3 chunks (Page 1) of every active resume are now automatically injected into the context.

---

## 3. Current Architecture Status

### 🔧 Backend Logic (`query_service.py`)
- **Query Decomposition**: Splits a compound user question into a "Tender Search" and a "Resume Search."
- **Saturating Search**: If an active document is small (<30 chunks), the system bypasses vector search and sends the **entire document** for 100% accuracy.
- **Interleaved Merging**: Enforces a 50/50 split between different source types in the final prompt.

### 🔧 AI Agent (`query_agent.py`)
- **Folder-Based Prompting**: Prompt uses massive `========= SECTION 1: TENDERS =========` headers to separate data types.
- **Anti-Laziness Rules**: Strictly forbids the AI from providing URLs/Links as a substitute for actual data extraction.

---

## 4. Pending Verification for Codex
1. **Multi-Source Stress Test**: Ask: *"Tell me the LOA definition clause from the glossary AND the Date of Birth of staff member Dharmireddi Sanyasi Naidu."*
2. **Success Metrics**:
   - **LOA Clause**: Should be extracted as "3.8.4" from Image 1.
   - **DOB**: Should be extracted as "01/07/1970" (Verified from Image 5).
   - **Project Costs**: Should differentiate between Tender (332.59 Cr) and Resume (424.99 Cr).

## 5. Files to Review
- `/app/services/query_service.py`: Main retrieval & merging logic.
- `/app/agents/query_agent.py`: Prompt engineering and source-labeling.
- `/app/rag/vector_store.py`: Enhanced hybrid search engine.
- `/app/rag/chunker.py`: Updated token-aware chunking limits.

---
**Status**: Backend is optimized; retrieval is deep and sectioned. Ready for final synthesis validation.

import os
import asyncio
from typing import List

from app.rag.loader import load_pdf_pages, flatten_pages
from app.rag.chunker import chunk_document_pages
from app.rag.embeddings import create_embeddings
from app.extraction.resume_extractor import extract_resume_data

async def evaluate_resume_processing(file_path: str):
    print(f"--- Evaluating resume file: {file_path} ---")
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    print(f"1. Loading PDF pages (using app.rag.loader.load_pdf_pages)...")
    extracted = load_pdf_pages(file_bytes, document_name="test_resume.pdf")
    print(f"   - Backend: {extracted.backend}")
    print(f"   - Pages: {len(extracted.pages)}")
    
    full_text = flatten_pages(extracted.pages)
    print(f"   - Full Text Length: {len(full_text)}")
    if not full_text.strip():
        print("   - Error: No text extracted!")
        return

    print(f"\n2. Chunking document (using app.rag.chunker.chunk_document_pages)...")
    chunk_records = chunk_document_pages(
        extracted.pages,
        document_type="resume",
        chunk_size=800,
        overlap=150,
        filename="test_resume.pdf",
        document_id=999, # Dummy ID
    )
    print(f"   - Chunks created: {len(chunk_records)}")
    if not chunk_records:
        print("   - Error: No chunks created!")
        return

    print(f"\n3. Creating embeddings (using app.rag.embeddings.create_embeddings)...")
    try:
        embeddings = create_embeddings([chunk["text"] for chunk in chunk_records])
        print(f"   - Embeddings created: {len(embeddings)}")
    except Exception as e:
        print(f"   - Error during embedding: {e}")

    print(f"\n4. Extraction check (LLM extraction via app.extraction.resume_extractor.extract_resume_data)...")
    try:
        # Note: This will call OpenAI or Ollama based on LLM_PROVIDER in .env
        structured_data = extract_resume_data(full_text)
        print(f"   - Structured extraction successful.")
        print(f"   - Candidate Name: {structured_data.get('candidate_name')}")
    except Exception as e:
        print(f"   - Error during LLM extraction: {e}")

if __name__ == "__main__":
    resume_file = "uploads/resumes/20260405_142705_467089_BE.pdf"
    if not os.path.exists(resume_file):
        # List files to pick another if this one moved
        resumes = [f for f in os.listdir("uploads/resumes") if f.endswith(".pdf")]
        if resumes:
            resume_file = os.path.join("uploads/resumes", resumes[0])
            
    asyncio.run(evaluate_resume_processing(resume_file))

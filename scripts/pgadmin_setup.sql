-- Tender RAG pgAdmin setup
--
-- Use this in pgAdmin Query Tool after creating the `tender_rag` database.
-- Connect the Query Tool to the `tender_rag` database, then run this file.

CREATE EXTENSION IF NOT EXISTS vector;

SELECT current_database() AS database_name;
SELECT extname FROM pg_extension WHERE extname = 'vector';

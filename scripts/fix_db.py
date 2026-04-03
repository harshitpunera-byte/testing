import os
import sys
from pathlib import Path
import psycopg2
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

def _psycopg2_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = parsed.scheme.split("+", 1)[0]
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))

def main():
    if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
        print("This script is for PostgreSQL. Please ensure DATABASE_URL is set in .env")
        return

    print(f"Connecting to database to apply fixes...")
    conn = psycopg2.connect(_psycopg2_url(DATABASE_URL))
    conn.autocommit = True
    
    with conn.cursor() as cur:
        # Fix missing generic_key in resume_education
        print("Checking for generic_key in resume_education...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='resume_education' AND column_name='generic_key';
        """)
        if not cur.fetchone():
            print("Adding generic_key to resume_education...")
            cur.execute("ALTER TABLE resume_education ADD COLUMN generic_key VARCHAR(128);")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_resume_education_generic_key ON resume_education (generic_key);")
        else:
            print("generic_key already exists.")

        # Fix column lengths in resume_projects
        print("Increasing column lengths in resume_projects...")
        cur.execute("ALTER TABLE resume_projects ALTER COLUMN project_name TYPE TEXT;")
        cur.execute("ALTER TABLE resume_projects ALTER COLUMN role TYPE VARCHAR(512);")
        cur.execute("ALTER TABLE resume_projects ALTER COLUMN domain TYPE VARCHAR(512);")
        
        print("Fixes applied successfully.")

    conn.close()

if __name__ == "__main__":
    main()

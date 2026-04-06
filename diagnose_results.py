import psycopg2
import json

def diagnose():
    try:
        conn = psycopg2.connect(
            user='postgres',
            password='postgres',
            host='localhost',
            port='5432',
            database='tender_rag'
        )
        cur = conn.cursor()
        
        # Check Document Statuses
        cur.execute("SELECT id, file_name, processing_status, document_type FROM documents")
        docs = cur.fetchall()
        print("\n--- Document Statuses ---")
        for doc in docs:
            print(f"ID: {doc[0]} | File: {doc[1]} | Status: {doc[2]} | Type: {doc[3]}")
            
        # Check Resume Profiles
        cur.execute("SELECT id, candidate_name, document_id FROM resume_profiles")
        profiles = cur.fetchall()
        print("\n--- Resume Profiles ---")
        for p in profiles:
            print(f"ID: {p[0]} | Name: {p[1]} | DocID: {p[2]}")
            
        # Check Education Keys
        cur.execute("SELECT resume_profile_id, generic_key, education_name FROM resume_education")
        edu = cur.fetchall()
        print("\n--- Education Data ---")
        for e in edu:
            print(f"ProfileID: {e[0]} | Key: {e[1]} | Name: {e[2]}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnose()

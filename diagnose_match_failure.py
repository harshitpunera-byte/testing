import psycopg2

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
        cur.execute("SELECT file_name, processing_status FROM documents WHERE document_type = 'resume'")
        print("\n--- Current Document Statuses ---")
        for row in cur.fetchall():
            print(f"File: {row[0]} | Status: {row[1]}")
            
        # Check Education Keys for the resumes
        cur.execute("SELECT generic_key, education_name FROM resume_education")
        print("\n--- Education 'generic_key' values recorded ---")
        for row in cur.fetchall():
            print(f"Key: {row[0]} | Original: {row[1]}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnose()

import psycopg2

def search_text():
    try:
        conn = psycopg2.connect(
            user='postgres',
            password='postgres',
            host='localhost',
            port='5432',
            database='tender_rag'
        )
        cur = conn.cursor()
        
        # Search for BTech keywords in the extracted text
        cur.execute("SELECT file_name, extracted_text FROM documents WHERE document_type = 'resume'")
        docs = cur.fetchall()
        print("\n--- BTech Keyword Search ---")
        for doc in docs:
            text = doc[1].lower() if doc[1] else ""
            found = 'btech' in text or 'b.tech' in text or 'bachelor of technology' in text
            print(f"File: {doc[0]} | BTech/Bachelor found: {found}")
            
        # Check Education Keys again for all records
        cur.execute("SELECT resume_profile_id, generic_key, education_name FROM resume_education")
        print("\n--- Raw Education Records ---")
        for row in cur.fetchall():
            print(f"Profile: {row[0]} | Key: {row[1]} | Name: {row[2]}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search_text()

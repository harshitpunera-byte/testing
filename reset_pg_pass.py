import psycopg2

try:
    conn = psycopg2.connect(
        user='postgres',
        host='localhost',
        port='5432',
        database='postgres',
        connect_timeout=5
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("ALTER USER postgres PASSWORD 'postgres';")
    cur.close()
    conn.close()
    print("PASSWORD RESET SUCCESSFUL")
except Exception as e:
    print(f"PASSWORD RESET FAILED: {e}")

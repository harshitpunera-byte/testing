import psycopg2

def test_password(p):
    print(f"Testing password: '{p}'")
    try:
        conn = psycopg2.connect(
            user='postgres',
            password=p,
            host='localhost',
            port='5432',
            database='postgres',
            connect_timeout=3
        )
        print(f"SUCCESS! The correct password is: '{p}'")
        conn.close()
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

passwords = ['', 'admin', 'password', '123456', 'root', 'postgres']
found = False
for pwd in passwords:
    if test_password(pwd):
        found = True
        break

if not found:
    print("ALL COMMON PASSWORDS FAILED. Please provide your PostgreSQL password.")

import os
import json
from urllib import request, error
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

def test_openai():
    print(f"Testing OpenAI with model: {OPENAI_MODEL}")
    print(f"API Key start: {OPENAI_API_KEY[:10]}...")
    
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "user", "content": "Return a JSON with one field 'status': 'ok'"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            print("Successfully received response:")
            print(body)
    except error.HTTPError as exc:
        print(f"HTTP Error {exc.code}")
        print(exc.read().decode("utf-8"))
    except Exception as exc:
        print(f"General Error: {type(exc).__name__}: {exc}")

if __name__ == "__main__":
    test_openai()

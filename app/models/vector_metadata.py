import json
import os

META_PATH = "vector_store/resume_metadata.json"

os.makedirs(os.path.dirname(META_PATH), exist_ok=True)

if os.path.exists(META_PATH):
    with open(META_PATH) as f:
        metadata = json.load(f)
else:
    metadata = []
    with open(META_PATH, "w") as f:
        json.dump(metadata, f)


def add_metadata(data):
    metadata.append(data)

    with open(META_PATH, "w") as f:
        json.dump(metadata, f)


def get_metadata():
    return metadata

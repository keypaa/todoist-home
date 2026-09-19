from fastapi import FastAPI
from app.db import init_db
app = FastAPI(title="OpenDoist")
init_db()
@app.get("/health")
def health():
    return {"ok": True}

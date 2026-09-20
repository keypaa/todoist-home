from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.db import init_db
app = FastAPI(title="OpenDoist")
init_db()

WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.exception_handler(HTTPException)
async def http_exc_handler(request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
def health():
    return {"ok": True}


from app.api_tasks import router as tasks_router
app.include_router(tasks_router)
from app.api_meta import router as meta_router
app.include_router(meta_router)
from app.sync import router as sync_router
app.include_router(sync_router)

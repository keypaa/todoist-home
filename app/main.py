from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from app.db import init_db
app = FastAPI(title="OpenDoist")
init_db()


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

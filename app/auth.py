from fastapi import Header, HTTPException


def require_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, {"error_tag": "UNAUTHORIZED", "error_code": 477, "error": "Unauthorized", "http_code": 401})
    tok = authorization[len("Bearer "):].strip()
    if not tok:
        raise HTTPException(401, {"error_tag": "UNAUTHORIZED", "error_code": 477, "error": "Unauthorized", "http_code": 401})
    return "1"

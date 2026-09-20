"""Projects/sections/labels CRUD + archive (OpenDoist V1 Task 7)."""
from fastapi import APIRouter, Depends, HTTPException
from app.auth import require_user
from app.models import new_id

router = APIRouter()

PROJECT_COLORS = {
    "berry_red", "red", "orange", "yellow", "olive_green", "lime_green",
    "green", "mint_green", "teal", "sky_blue", "light_blue", "blue",
    "grape", "violet", "lavender", "magenta", "salmon", "charcoal",
    "grey", "taupe",
}
PROJECT_LAYOUTS = {"list", "board", "calendar"}


def _coerce_favorite(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes")
    return bool(v)


def _validate_color(color):
    if color not in PROJECT_COLORS:
        raise HTTPException(400, "invalid color")


def _validate_layout(layout):
    if layout not in PROJECT_LAYOUTS:
        raise HTTPException(400, "invalid layout")


def _con():
    from app.api_tasks import _con as _tasks_con

    return _tasks_con()


def _project_to_api(r):
    keys = r.keys() if hasattr(r, "keys") else []
    def _get(col, default=None):
        try:
            if col in keys:
                v = r[col]
                return default if v is None and default is not None else v
            return default
        except Exception:
            return default
    fav = _get("is_favorite", 0)
    return {
        "id": r["id"],
        "name": r["name"],
        "description": _get("description", "") or "",
        "color": _get("color", "charcoal") or "charcoal",
        "workspace": _get("workspace", "My Projects") or "My Projects",
        "parent_id": _get("parent_id", None),
        "access": _get("access", "Restricted") or "Restricted",
        "is_favorite": bool(fav) if not isinstance(fav, bool) else fav,
        "layout": _get("layout", "list") or "list",
        "is_archived": bool(r["is_archived"]),
        "is_deleted": bool(r["is_deleted"]),
        "order_key": r["order_key"] if "order_key" in r.keys() else "a0",
    }


def _section_to_api(r):
    return {
        "id": r["id"],
        "project_id": r["project_id"],
        "name": r["name"],
        "is_archived": bool(r["is_archived"]),
        "is_deleted": bool(r["is_deleted"]),
    }


def _label_to_api(r):
    return {"id": r["id"], "name": r["name"], "is_deleted": bool(r["is_deleted"])}


# ---- projects ----

@router.post("/api/v1/projects")
def create_project(body: dict, uid: str = Depends(require_user)):
    name = (body.get("name") or "").strip() if isinstance(body, dict) else ""
    if not name:
        raise HTTPException(400, "name required")
    description = body.get("description", "")
    color = body.get("color", "charcoal")
    workspace = body.get("workspace", "My Projects")
    parent_id = body.get("parent_id")
    access = body.get("access", "Restricted")
    is_favorite = _coerce_favorite(body.get("is_favorite", False))
    layout = body.get("layout", "list")
    if description is None:
        description = ""
    description = str(description)
    if color is None or (isinstance(color, str) and not color.strip()):
        color = "charcoal"
    color = str(color).strip()
    _validate_color(color)
    if workspace is None or (isinstance(workspace, str) and not workspace.strip()):
        workspace = "My Projects"
    workspace = str(workspace)
    if parent_id is not None:
        parent_id = str(parent_id) if str(parent_id).strip() else None
    if access is None or (isinstance(access, str) and not access.strip()):
        access = "Restricted"
    access = str(access)
    if layout is None or (isinstance(layout, str) and not layout.strip()):
        layout = "list"
    layout = str(layout).strip()
    _validate_layout(layout)
    con = _con()
    pid = new_id()
    con.execute(
        "INSERT INTO projects(id,user_id,name,description,color,workspace,parent_id,access,is_favorite,layout) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (pid, uid, name, description, color, workspace, parent_id, access, 1 if is_favorite else 0, layout),
    )
    con.commit()
    row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return _project_to_api(row)


@router.get("/api/v1/projects")
def list_projects(uid: str = Depends(require_user)):
    con = _con()
    rows = con.execute(
        "SELECT * FROM projects WHERE user_id=? AND is_deleted=0", (uid,)
    ).fetchall()
    return [_project_to_api(r) for r in rows]


@router.get("/api/v1/projects/{pid}")
def get_project(pid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)
    ).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    return _project_to_api(r)


@router.post("/api/v1/projects/{pid}")
def update_project(pid: str, body: dict, uid: str = Depends(require_user)):
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid body")
    con = _con()
    r = con.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)
    ).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    if "name" in body and body["name"] is not None:
        name = str(body["name"]).strip()
        if not name:
            raise HTTPException(400, "name required")
        con.execute("UPDATE projects SET name=? WHERE id=?", (name, pid))
    if "description" in body:
        v = body["description"]
        con.execute("UPDATE projects SET description=? WHERE id=?", ("" if v is None else str(v), pid))
    if "color" in body and body["color"] is not None:
        color = str(body["color"]).strip() or "charcoal"
        _validate_color(color)
        con.execute("UPDATE projects SET color=? WHERE id=?", (color, pid))
    if "workspace" in body and body["workspace"] is not None:
        ws = str(body["workspace"]).strip() or "My Projects"
        con.execute("UPDATE projects SET workspace=? WHERE id=?", (ws, pid))
    if "parent_id" in body:
        pv = body["parent_id"]
        pv = None if pv is None or (isinstance(pv, str) and not pv.strip()) else str(pv)
        con.execute("UPDATE projects SET parent_id=? WHERE id=?", (pv, pid))
    if "access" in body and body["access"] is not None:
        av = str(body["access"]).strip() or "Restricted"
        con.execute("UPDATE projects SET access=? WHERE id=?", (av, pid))
    if "is_favorite" in body and body["is_favorite"] is not None:
        con.execute("UPDATE projects SET is_favorite=? WHERE id=?", (1 if _coerce_favorite(body["is_favorite"]) else 0, pid))
    if "layout" in body and body["layout"] is not None:
        layout = str(body["layout"]).strip() or "list"
        _validate_layout(layout)
        con.execute("UPDATE projects SET layout=? WHERE id=?", (layout, pid))
    con.commit()
    row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return _project_to_api(row)


@router.delete("/api/v1/projects/{pid}")
def delete_project(pid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)
    ).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    con.execute("UPDATE projects SET is_deleted=1 WHERE id=?", (pid,))
    con.commit()
    return {"ok": True}


@router.post("/api/v1/projects/{pid}/archive")
def archive_project(pid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)
    ).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    con.execute("UPDATE projects SET is_archived=1 WHERE id=?", (pid,))
    con.commit()
    row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return _project_to_api(row)


@router.post("/api/v1/projects/{pid}/unarchive")
def unarchive_project(pid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute(
        "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)
    ).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    con.execute("UPDATE projects SET is_archived=0 WHERE id=?", (pid,))
    con.commit()
    row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return _project_to_api(row)


# ---- sections ----

@router.post("/api/v1/sections")
def create_section(body: dict, uid: str = Depends(require_user)):
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid body")
    project_id = body.get("project_id")
    name = (body.get("name") or "").strip()
    if not project_id:
        raise HTTPException(400, "project_id required")
    if not name:
        raise HTTPException(400, "name required")
    con = _con()
    prow = con.execute(
        "SELECT * FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    if not prow or prow["is_deleted"]:
        raise HTTPException(404, "project not found")
    sid = new_id()
    con.execute(
        "INSERT INTO sections(id,project_id,name) VALUES(?,?,?)",
        (sid, project_id, name),
    )
    con.commit()
    row = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    return _section_to_api(row)


@router.get("/api/v1/sections")
def list_sections(
    uid: str = Depends(require_user), project_id: str | None = None
):
    con = _con()
    if project_id:
        rows = con.execute(
            "SELECT * FROM sections WHERE project_id=? AND is_deleted=0",
            (project_id,),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM sections WHERE is_deleted=0"
        ).fetchall()
    return [_section_to_api(r) for r in rows]


@router.get("/api/v1/sections/{sid}")
def get_section(sid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    return _section_to_api(r)


@router.post("/api/v1/sections/{sid}")
def update_section(sid: str, body: dict, uid: str = Depends(require_user)):
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid body")
    con = _con()
    r = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    if "name" in body and body["name"] is not None:
        name = str(body["name"]).strip()
        if not name:
            raise HTTPException(400, "name required")
        con.execute("UPDATE sections SET name=? WHERE id=?", (name, sid))
    if "project_id" in body and body["project_id"]:
        prow = con.execute(
            "SELECT * FROM projects WHERE id=?", (body["project_id"],)
        ).fetchone()
        if not prow or prow["is_deleted"]:
            raise HTTPException(404, "project not found")
        con.execute(
            "UPDATE sections SET project_id=? WHERE id=?",
            (body["project_id"], sid),
        )
    con.commit()
    row = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    return _section_to_api(row)


@router.delete("/api/v1/sections/{sid}")
def delete_section(sid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    con.execute("UPDATE sections SET is_deleted=1 WHERE id=?", (sid,))
    con.commit()
    return {"ok": True}


@router.post("/api/v1/sections/{sid}/archive")
def archive_section(sid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    con.execute("UPDATE sections SET is_archived=1 WHERE id=?", (sid,))
    con.commit()
    row = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    return _section_to_api(row)


@router.post("/api/v1/sections/{sid}/unarchive")
def unarchive_section(sid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    con.execute("UPDATE sections SET is_archived=0 WHERE id=?", (sid,))
    con.commit()
    row = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    return _section_to_api(row)


# ---- labels ----

@router.post("/api/v1/labels")
def create_label(body: dict, uid: str = Depends(require_user)):
    name = (body.get("name") or "").strip() if isinstance(body, dict) else ""
    if not name:
        raise HTTPException(400, "name required")
    con = _con()
    lid = new_id()
    con.execute(
        "INSERT INTO labels(id,user_id,name) VALUES(?,?,?)", (lid, uid, name)
    )
    con.commit()
    row = con.execute("SELECT * FROM labels WHERE id=?", (lid,)).fetchone()
    return _label_to_api(row)


@router.get("/api/v1/labels")
def list_labels(uid: str = Depends(require_user)):
    con = _con()
    rows = con.execute(
        "SELECT * FROM labels WHERE user_id=? AND is_deleted=0", (uid,)
    ).fetchall()
    return [_label_to_api(r) for r in rows]


@router.get("/api/v1/labels/{lid}")
def get_label(lid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute(
        "SELECT * FROM labels WHERE id=? AND user_id=?", (lid, uid)
    ).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    return _label_to_api(r)


@router.post("/api/v1/labels/{lid}")
def update_label(lid: str, body: dict, uid: str = Depends(require_user)):
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid body")
    con = _con()
    r = con.execute(
        "SELECT * FROM labels WHERE id=? AND user_id=?", (lid, uid)
    ).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    if "name" in body and body["name"] is not None:
        name = str(body["name"]).strip()
        if not name:
            raise HTTPException(400, "name required")
        con.execute("UPDATE labels SET name=? WHERE id=?", (name, lid))
        con.commit()
    row = con.execute("SELECT * FROM labels WHERE id=?", (lid,)).fetchone()
    return _label_to_api(row)


@router.delete("/api/v1/labels/{lid}")
def delete_label(lid: str, uid: str = Depends(require_user)):
    con = _con()
    r = con.execute(
        "SELECT * FROM labels WHERE id=? AND user_id=?", (lid, uid)
    ).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    con.execute("UPDATE labels SET is_deleted=1 WHERE id=?", (lid,))
    con.commit()
    return {"ok": True}

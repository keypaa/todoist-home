# omatasks fork patch — point omatasks at OpenDoist localhost

Target: https://github.com/crmne/omatasks (our ONE maintained fork;
we do NOT fork omarchy-todoist — it is already API-compatible).

## Change

Replace the hardcoded Todoist base URL:

```
https://api.todoist.com/api/v1
```

with a configurable value:

```python
import os
OPENDOIST_API = os.environ.get("OPENDOIST_API", "http://localhost:8000/api/v1")
```

- Default (no env set): `http://localhost:8000/api/v1` → OpenDoist on this machine.
- Override: `OPENDOIST_API=https://api.todoist.com/api/v1 omatasks ...` restores cloud.
- Handle the trailing slash: strip one trailing `/` from the env value before
  appending endpoint paths (`/sync`, `/tasks/quick`, `/tasks/{id}/close`, …),
  so both `.../api/v1` and `.../api/v1/` work.

Apply at every place the fork constructs a Todoist URL (sync client, quick-add,
task close/reopen, reorder/bulk paths) — `grep -rn "api.todoist.com"` must return
no hits after the patch.

## Keep as-is

- **Form-encoding:** `POST /sync` stays `application/x-www-form-urlencoded` with
  `sync_token`, `resource_types` (JSON string), and `commands` (JSON string) fields.
  Do NOT convert to JSON bodies — OpenDoist's sync parser expects form fields.
- **Auth header:** keep sending `Authorization: Bearer <token>` on every call.
  Any non-empty token is accepted (single local user); missing/empty → 401
  `{"error_tag":"UNAUTHORIZED","error_code":477,...}`.

## Validate

1. Start OpenDoist: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
2. Token check (mirrors omatasks `connectToken`):
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/sync \
     -H "Authorization: Bearer local-dev" \
     --data-urlencode "sync_token=*" \
     --data-urlencode 'resource_types=["user"]'
   ```
   Must return `200` with a `user{id:"1",...}` object. If this fails, the base URL
   or auth header is wrong — fix those before anything else.
3. Full refresh (mirrors omatasks `refresh()`):
   `resource_types='["items","projects","sections","labels","user","collaborators","reminders","completed_info"]'`
   must return `200` with `items/projects/sections/labels/user/sync_token`.
4. Automated gate: `python -m pytest tests/test_plugin_compat.py -q` replays the
   connect → quick-add (`auto_reminder` + `X-Request-Id`) → refresh → close
   sequence against localhost and must be green.
5. Manual: forked omatasks against localhost lists, completes, adds, and reorders
   tasks identically to cloud state.

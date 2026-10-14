"""FastAPI app: upload UI, /api/send, and self-hosted media/ + static/ mounts."""
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import aiofiles
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import excel_store

log = logging.getLogger("discord_bot")

app = FastAPI(title="discord media uploader")

STATIC_DIR = os.path.join(config.BASE_DIR, "static")
os.makedirs(config.MEDIA_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")


def _sanitize(name: str) -> str:
    name = os.path.basename(name or "upload.bin")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "upload.bin"
    return name[-100:]


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/config")
async def api_config():
    return {
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "discord_upload_limit_mb": config.DISCORD_UPLOAD_LIMIT_MB,
        "public_base_url": config.PUBLIC_BASE_URL,
        "links_local_only": "127.0.0.1" in config.PUBLIC_BASE_URL
        or "localhost" in config.PUBLIC_BASE_URL,
        "channel_configured": bool(config.CHANNEL_ID),
    }


@app.get("/api/log")
async def api_log(limit: int = 50):
    rows = await asyncio.to_thread(excel_store.read_all, config.DATA_XLSX, limit)
    return {"rows": rows}


@app.post("/api/send")
async def api_send(request: Request, files: list[UploadFile] = File(...)):
    queue: asyncio.Queue = request.app.state.upload_queue
    results: list = []
    items: list = []

    for uf in files:
        original = _sanitize(uf.filename or "upload.bin")
        mime = uf.content_type or "application/octet-stream"
        if not mime.startswith(config.ALLOWED_MIME_PREFIXES):
            results.append({"original_name": original, "status": "rejected",
                            "error": f"Only images/videos accepted (got {mime})"})
            continue

        stored = f"{uuid.uuid4().hex[:8]}_{original}"
        path = os.path.join(config.MEDIA_DIR, stored)
        size = 0
        too_big = False
        try:
            async with aiofiles.open(path, "wb") as out:
                while True:
                    chunk = await uf.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > config.MAX_UPLOAD_BYTES:
                        too_big = True
                        break
                    await out.write(chunk)
        finally:
            await uf.close()

        if too_big or size == 0:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
            reason = (f"Exceeds {config.MAX_UPLOAD_MB} MB limit" if too_big
                      else "Empty file")
            results.append({"original_name": original, "status": "rejected",
                            "error": reason})
            continue

        try:
            row = await asyncio.to_thread(excel_store.append_row, config.DATA_XLSX, {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "original_name": original,
                "stored_name": stored,
                "size_bytes": size,
                "mime_type": mime,
                "mode": "",
                "url": "",
                "message_id": "",
                "status": "pending",
                "error": "",
            })
        except Exception as exc:
            log.exception("Excel append failed")
            row = 0
            results.append({"original_name": original, "stored_name": stored,
                            "size_bytes": size, "status": "queued",
                            "warning": f"Excel log failed: {exc}"})
        else:
            results.append({"original_name": original, "stored_name": stored,
                            "size_bytes": size, "status": "queued"})
        items.append({"original_name": original, "stored_name": stored,
                      "size_bytes": size, "mime_type": mime, "row": row})

    if items:
        await queue.put({"items": items})
    return {"results": results}

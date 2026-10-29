"""AI banner images for charts and themes (Gemini by default, or OpenAI).

The key stays on the server: the browser only ever talks to muzplayer. Nothing here runs by
itself; every image is made because an admin pressed a button (each one costs money).
"""

import base64
import io
import json
import logging
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

from .config import settings

log = logging.getLogger(__name__)

TIMEOUT = 180
BANNER_SIZE = (1600, 900)  # 16:9, shown cropped to wider boxes on large screens
CANDIDATE_TTL = 3600
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
OPENAI_URL = "https://api.openai.com/v1/images"

_busy = threading.Lock()  # one image at a time: a double click must not be billed twice


class AiError(Exception):
    """Carries only a code for the frontend."""


def provider() -> str:
    return "openai" if settings.ai_provider == "openai" else "gemini"


def model() -> str:
    return settings.openai_image_model if provider() == "openai" else settings.gemini_image_model


def configured() -> bool:
    return bool(settings.openai_api_key if provider() == "openai" else settings.gemini_api_key)


def banner_file(banner_id: int) -> Path:
    return settings.cover_dir / f"banner_{banner_id}.jpg"


def candidate_dir() -> Path:
    return settings.data_dir / "banner_tmp"


def candidate_file(token: str) -> Path | None:
    if len(token) != 32 or not all(c in "0123456789abcdef" for c in token):
        return None
    return candidate_dir() / f"{token}.jpg"


def _post(url: str, body: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:  # noqa: S310 - fixed API hosts
            return json.loads(res.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(800).decode("utf-8", "replace")
        log.warning("ai banner: %s %s: %s", provider(), exc.code, detail)
        if exc.code in (401, 403):
            raise AiError("ai_unauthorized") from None
        if exc.code == 429:
            raise AiError("ai_quota") from None
        if exc.code == 400:  # a refused prompt, or a model/field this API version doesn't take
            raise AiError("ai_rejected") from None
        raise AiError("ai_bad_response") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AiError("ai_unreachable") from None
    except ValueError:
        raise AiError("ai_bad_response") from None


def _last_image(data) -> bytes | None:
    """The last image anywhere in the response. Gemini's interactions API puts them in
    steps[].content[] as {"type": "image", "data": base64}; older shapes use inline_data."""
    found = None

    def walk(node):
        nonlocal found
        if isinstance(node, dict):
            mime = str(node.get("mime_type") or node.get("mimeType") or "")
            if isinstance(node.get("data"), str) and (node.get("type") == "image" or mime.startswith("image/")):
                found = node["data"]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return base64.b64decode(found) if found else None


def _gemini(prompt: str, images: list[bytes]) -> bytes:
    parts = [{"type": "text", "text": prompt}] + [
        {"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(img).decode()} for img in images
    ]
    body = {
        "model": settings.gemini_image_model,
        "input": parts,
        "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": "16:9", "image_size": "2K"},
    }
    data = _post(
        GEMINI_URL,
        json.dumps(body).encode(),
        {"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
    )
    image = _last_image(data)
    if image is None:
        raise AiError("ai_no_image")  # usually a safety refusal: the response has text only
    return image


def _openai(prompt: str, images: list[bytes]) -> bytes:
    auth = {"Authorization": f"Bearer {settings.openai_api_key}"}
    fields = {"model": settings.openai_image_model, "prompt": prompt, "size": "1536x864", "output_format": "jpeg"}
    if not images:
        data = _post(f"{OPENAI_URL}/generations", json.dumps(fields).encode(), {**auth, "Content-Type": "application/json"})
    else:
        boundary = uuid.uuid4().hex
        out = io.BytesIO()
        for name, value in fields.items():
            out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        for i, img in enumerate(images):
            out.write(
                f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="{i}.jpg"\r\n'
                "Content-Type: image/jpeg\r\n\r\n".encode()
            )
            out.write(img + b"\r\n")
        out.write(f"--{boundary}--\r\n".encode())
        data = _post(f"{OPENAI_URL}/edits", out.getvalue(), {**auth, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    b64 = ((data.get("data") or [{}])[0] or {}).get("b64_json")
    if not b64:
        raise AiError("ai_no_image")
    return base64.b64decode(b64)


def _normalize(data: bytes) -> bytes:
    """Center-crops to 16:9 and stores a 1600x900 JPEG."""
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        raise AiError("ai_bad_response") from None
    w, h = image.size
    target = BANNER_SIZE[0] / BANNER_SIZE[1]
    if w / h > target:
        cut = int(h * target)
        image = image.crop(((w - cut) // 2, 0, (w - cut) // 2 + cut, h))
    else:
        cut = int(w / target)
        image = image.crop((0, (h - cut) // 2, w, (h - cut) // 2 + cut))
    image = image.resize(BANNER_SIZE, Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=88)
    return out.getvalue()


def reference_jpeg(path: Path, box: int = 1024) -> bytes | None:
    """An image file made small enough to send along as a reference."""
    try:
        image = Image.open(path).convert("RGB")
    except Exception:
        return None
    image.thumbnail((box, box))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def _clean_candidates() -> None:
    cutoff = time.time() - CANDIDATE_TTL
    for f in candidate_dir().glob("*.jpg"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _make(prompt: str, images: list[bytes]) -> str:
    """Makes one image and keeps it as a candidate. Returns its token."""
    raw = _openai(prompt, images) if provider() == "openai" else _gemini(prompt, images)
    data = _normalize(raw)
    candidate_dir().mkdir(parents=True, exist_ok=True)
    _clean_candidates()
    token = secrets.token_hex(16)
    candidate_file(token).write_bytes(data)
    return token


# job id -> {"status": running|done|failed, "candidate", "error"}; a few recent ones only.
# Runs in the background so a slow image (up to TIMEOUT) never hits a reverse proxy's
# read timeout: the page polls instead of holding one long request open.
jobs: dict[str, dict] = {}


def _run(job_id: str, prompt: str, images: list[bytes]) -> None:
    try:
        jobs[job_id].update(status="done", candidate=_make(prompt, images))
    except AiError as exc:
        jobs[job_id].update(status="failed", error=str(exc))
    except Exception:
        log.exception("ai banner failed")
        jobs[job_id].update(status="failed", error="ai_bad_response")
    finally:
        _busy.release()


def start(prompt: str, images: list[bytes]) -> str:
    """Starts making one image. Returns the job id to poll."""
    if not configured():
        raise AiError("ai_off")
    if not _busy.acquire(blocking=False):
        raise AiError("ai_busy")
    for old in list(jobs)[:-10]:
        jobs.pop(old, None)
    job_id = secrets.token_hex(8)
    jobs[job_id] = {"status": "running", "candidate": None, "error": None}
    threading.Thread(target=_run, args=(job_id, prompt, images), daemon=True, name="ai-banner").start()
    return job_id

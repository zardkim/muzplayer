"""JSON answers from the text model an admin set up for banners (Admin → integrations): extract.py
asks it for a video's artist and title."""

import json
import logging
import re

from . import ai_banner, appconf
from .ai_banner import AiError

log = logging.getLogger(__name__)

GEMINI_URL = ai_banner.GEMINI_URL
OPENAI_URL = "https://api.openai.com/v1/responses"


def ask_json(system: str, prompt: str, schema: dict, name: str) -> dict:
    """One answer from the set-up text model, as JSON in the given schema."""
    which = appconf.provider()
    key = appconf.get(f"{which}_api_key")
    if which == "openai":
        body = {
            "model": appconf.text_model("openai"),
            "input": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "text": {"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        }
        data = ai_banner._post(OPENAI_URL, json.dumps(body).encode(), {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        texts = [c.get("text", "") for item in data.get("output", []) for c in item.get("content") or [] if c.get("type") in ("output_text", "text")]
    else:
        body = {
            "model": appconf.text_model("gemini"),
            "input": f"{system}\nRequest: {prompt}",
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
        }
        data = ai_banner._post(GEMINI_URL, json.dumps(body).encode(), {"x-goog-api-key": key, "Content-Type": "application/json"})
        texts = [
            c.get("text", "")
            for step in data.get("steps", [])
            if step.get("type") == "model_output"
            for c in step.get("content") or []
            if c.get("type") == "text"
        ]
    # the answer's last JSON object: also when wrapped in ```json fences or a sentence, or (another
    # shape of the response) in any text the response holds
    for text in [*reversed(texts), *reversed(_texts(data))]:
        found = _json_in(text)
        if found is not None:
            return found
    log.warning("ai: no JSON in the answer of %s: %s", which, json.dumps(data, ensure_ascii=False)[:800])
    raise AiError("ai_bad_response")


def _texts(node) -> list[str]:
    """Every "text" (or "output_text") string anywhere in a response, in order."""
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("text", "output_text") and isinstance(v, str):
                out.append(v)
            else:
                out += _texts(v)
    elif isinstance(node, list):
        for v in node:
            out += _texts(v)
    return out


def _json_in(text: str) -> dict | None:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    for candidate in (t, t[t.find("{") : t.rfind("}") + 1] if "{" in t else ""):
        try:
            found = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None

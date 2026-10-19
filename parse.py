"""Turn a counter complaint into a fault the graph can check.

Gemma proposes the fault. A word that is actually in the complaint wins.
The model never sets the price, the warranty, or the outcome.
"""

from __future__ import annotations

import json
import os
import re

import httpx

MODEL = os.environ.get("GEMMA_MODEL", "gemma3:4b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
FAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "phone": {"type": "string"},
        "customer": {"type": "string"},
        "fault": {
            "type": "string",
            "enum": ["touch", "battery", "charging", "unknown"],
        },
    },
    "required": ["phone", "customer", "fault"],
}

FAULT_WORDS = (
    ("charging", ("charging port", "charge port", "charging")),
    ("battery", ("battery",)),
    ("touch", ("touch", "screen", "display")),
)

PHONE_RE = re.compile(r"(?<!\d)([6-9]\d{9})(?!\d)")


def keywords(text: str) -> str:
    low = text.lower()
    for fault, words in FAULT_WORDS:
        if any(word in low for word in words):
            return fault
    return ""


def grounded(fault: str, text: str) -> bool:
    if fault not in {"touch", "battery", "charging"}:
        return False
    low = text.lower()
    words = dict(FAULT_WORDS)[fault]
    return any(word in low for word in words)


def parse_local(text: str, customers: list[dict]) -> dict:
    low = text.lower()
    phone = ""
    found = PHONE_RE.search(text)
    if found:
        phone = found.group(1)
    name = ""
    for customer in customers:
        full = customer["name"].lower()
        first = full.split()[0]
        if full in low or re.search(rf"\b{re.escape(first)}\b", low):
            name = customer["name"]
            break
    return {
        "phone": phone,
        "name": name,
        "fault": keywords(text),
        "source": "keywords",
        "model": "",
        "gemma_fault": "",
        "grounded": True,
    }


def ask_gemma(text: str) -> dict | None:
    if os.environ.get("DOBARA_SKIP_GEMMA") == "1":
        return None
    prompt = (
        "Read the complaint. fault must be touch, battery, charging, or unknown. "
        "phone is 10 digits or an empty string. customer is the name or an empty string. "
        "Use a fault only if the complaint says that problem.\n"
        f"Complaint: {text}"
    )
    try:
        response = httpx.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "stream": False,
                "format": FAULT_SCHEMA,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20.0,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.split("\n", 1)[-1]
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def parse_complaint(text: str, customers: list[dict]) -> dict:
    local = parse_local(text, customers)
    heard = ask_gemma(text)
    if not heard:
        return local
    fault = str(heard.get("fault") or "").strip().lower()
    phone = re.sub(r"\D", "", str(heard.get("phone") or ""))
    if len(phone) > 10:
        phone = phone[-10:]
    name = str(heard.get("customer") or "").strip()
    used_model = grounded(fault, text)
    parsed = {
        "phone": local["phone"] or (phone if len(phone) == 10 else ""),
        "name": local["name"] or name,
        "fault": fault if used_model else local["fault"],
        "source": "gemma" if used_model else "keywords",
        "model": MODEL if used_model or fault else "",
        "gemma_fault": fault,
        "grounded": used_model,
    }
    if parsed["source"] == "keywords" and heard:
        parsed["model"] = MODEL
        parsed["source"] = "keywords_after_gemma"
    return parsed

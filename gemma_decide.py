"""Gemma, through OpenRouter, decides from the live rows. It does not invent jobs."""

from __future__ import annotations

import json
import os
from datetime import date

import httpx

MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-3-4b-it")
URL = "https://openrouter.ai/api/v1/chat/completions"

SCHEMA = {
    "type": "object",
    "properties": {
        "fault": {"type": "string", "enum": ["touch", "battery", "charging"]},
        "outcome": {
            "type": "string",
            "enum": ["collect_first", "free_comeback", "labor_only", "new_paid"],
        },
        "amount_inr": {"type": "integer"},
        "assignee": {"type": "string"},
        "based_on": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["fault", "outcome", "amount_inr", "assignee", "based_on", "summary"],
    "additionalProperties": False,
}


def job_facts(jobs: list[dict], today: date) -> list[dict]:
    facts = []
    for job in jobs:
        closed = job.get("closed_on")
        age = None
        if closed:
            age = (today - date.fromisoformat(str(closed)[:10])).days
        facts.append(
            {
                "id": job["id"],
                "fault": job["fault"],
                "status": job["status"],
                "paid": job["paid"],
                "amount_inr": job["amount_inr"],
                "technician": job.get("technician") or "",
                "part_name": job.get("part_name") or "",
                "supplier": job.get("supplier") or "",
                "warranty_days": job.get("warranty_days"),
                "model": job.get("model") or "",
                "age_days": age,
            }
        )
    return facts


def messages(policy: dict, customer: dict, jobs: list[dict], technicians: list[dict], complaint: str, today: date) -> list[dict]:
    payload = {
        "today": today.isoformat(),
        "policy": {
            "comeback_days": policy["comeback_days"],
            "labor_inr": policy["labor_inr"],
            "quotes_inr": {
                "touch": policy["touch_quote"],
                "battery": policy["battery_quote"],
                "charging": policy["charging_quote"],
            },
        },
        "customer": {"name": customer["name"], "phone": customer["phone"], "model": customer["model"]},
        "technicians": [{"name": tech["name"], "skills": tech.get("skills") or []} for tech in technicians],
        "jobs": job_facts(jobs, today),
        "complaint": complaint,
    }
    rules = (
        "Decide the counter slip from the JSON records. Use only those jobs and technicians. "
        "age_days is already calculated. Apply the rules in order: "
        "1. If any job has paid false and status open, outcome is collect_first, "
        "amount_inr is that job's amount_inr, based_on is that job id, assignee is empty. "
        "2. Else if a paid closed job has the same fault and age_days is less than or equal to "
        "comeback_days, outcome is free_comeback, amount_inr is 0, assignee is that job's technician, "
        "based_on is that job id. "
        "3. Else if a paid closed job has the same fault and warranty_days is a number and age_days "
        "is less than or equal to warranty_days, outcome is labor_only, amount_inr is labor_inr, "
        "assignee is that technician, based_on is that job id. "
        "4. Else outcome is new_paid, amount_inr is the quote for the fault, based_on is empty, "
        "and assignee is a technician whose skills include the fault. "
        "summary is two sentences a counter can read aloud. It must name the job id when there is one."
    )
    return [
        {"role": "system", "content": rules},
        {"role": "user", "content": json.dumps(payload)},
    ]


def _parse(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Gemma did not return an object.")
    return data


def validate(decision: dict, jobs: list[dict], technicians: list[dict]) -> str | None:
    if decision.get("fault") not in {"touch", "battery", "charging"}:
        return "Gemma returned a fault that is not touch, battery, or charging."
    if decision.get("outcome") not in {"collect_first", "free_comeback", "labor_only", "new_paid"}:
        return "Gemma returned an outcome the counter does not use."
    known = {job["id"] for job in jobs}
    based = decision.get("based_on") or []
    if not isinstance(based, list):
        return "based_on must be a list of job ids."
    missing = [job_id for job_id in based if job_id not in known]
    if missing:
        return "Gemma cited a job that is not on this customer's book: " + ", ".join(missing)
    unpaid = [job for job in jobs if job.get("status") == "open" and not job.get("paid")]
    if unpaid and decision["outcome"] != "collect_first":
        return "This customer still has an unpaid job. Gemma has to collect that first."
    if decision["outcome"] == "collect_first" and not unpaid:
        return "Gemma chose collect_first, and this customer has no unpaid job."
    assignee = (decision.get("assignee") or "").strip()
    names = {tech["name"] for tech in technicians}
    if assignee and assignee not in names:
        return "Gemma assigned someone who is not on the floor."
    if not str(decision.get("summary") or "").strip():
        return "Gemma did not write a summary."
    return None


def decide(policy: dict, customer: dict, jobs: list[dict], technicians: list[dict], complaint: str, today: date | None = None) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY.")
    today = today or date.today()
    body = {
        "model": MODEL,
        "temperature": 0,
        "messages": messages(policy, customer, jobs, technicians, complaint, today),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "counter_decision", "strict": True, "schema": SCHEMA},
        },
    }
    response = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=40.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    content = response.json()["choices"][0]["message"]["content"]
    parsed = _parse(content)
    problem = validate(parsed, jobs, technicians)
    if problem:
        raise RuntimeError(problem)
    parsed["assignee"] = (parsed.get("assignee") or "").strip()
    parsed["model"] = MODEL
    return parsed

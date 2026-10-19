"""Supabase REST. The service role writes. The browser only listens."""

from __future__ import annotations

import os
from datetime import date

import httpx

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def configured() -> bool:
    return bool(URL and SERVICE)


def _headers() -> dict:
    return {
        "apikey": SERVICE,
        "Authorization": f"Bearer {SERVICE}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _request(method: str, table: str, *, params: dict | None = None, body=None):
    if not configured():
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    response = httpx.request(
        method,
        f"{URL}/rest/v1/{table}",
        headers=_headers(),
        params=params,
        json=body,
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    if not response.content:
        return []
    return response.json()


def policy() -> dict:
    rows = _request("GET", "policy", params={"id": "eq.1", "select": "*"})
    if not rows:
        raise RuntimeError("The policy row is missing. Run schema.sql.")
    return rows[0]


def save_policy(fields: dict) -> dict:
    rows = _request(
        "PATCH",
        "policy",
        params={"id": "eq.1"},
        body={
            "comeback_days": int(fields["comeback_days"]),
            "labor_inr": int(fields["labor_inr"]),
            "touch_quote": int(fields["touch_quote"]),
            "battery_quote": int(fields["battery_quote"]),
            "charging_quote": int(fields["charging_quote"]),
        },
    )
    return rows[0]


def technicians() -> list[dict]:
    return _request("GET", "technicians", params={"select": "id,name,skills", "order": "name.asc"})


def add_technician(name: str, skills: list[str]) -> dict:
    rows = _request(
        "POST",
        "technicians",
        body={"name": name.strip(), "skills": skills},
    )
    return rows[0]


def customers() -> list[dict]:
    return _request(
        "GET",
        "customers",
        params={"select": "id,name,phone,model,imei,created_at", "order": "created_at.desc"},
    )


def add_customer(name: str, phone: str, model: str, imei: str) -> dict:
    rows = _request(
        "POST",
        "customers",
        body={"name": name.strip(), "phone": phone, "model": model.strip(), "imei": imei.strip()},
    )
    return rows[0]


def customer_by_phone(phone: str) -> dict | None:
    rows = _request(
        "GET",
        "customers",
        params={"phone": f"eq.{phone}", "select": "id,name,phone,model,imei"},
    )
    return rows[0] if rows else None


def jobs_for(phone: str) -> list[dict]:
    return _request(
        "GET",
        "jobs",
        params={
            "phone": f"eq.{phone}",
            "select": "*",
            "order": "opened_on.desc",
        },
    )


def all_jobs() -> list[dict]:
    return _request("GET", "jobs", params={"select": "*", "order": "created_at.desc", "limit": "40"})


def add_job(customer: dict, fields: dict) -> dict:
    paid = bool(fields.get("paid"))
    closed = fields.get("closed_on") or None
    if paid and not closed:
        closed = date.today().isoformat()
    body = {
        "id": fields["id"],
        "customer_id": customer["id"],
        "phone": customer["phone"],
        "customer_name": customer["name"],
        "model": customer["model"],
        "fault": fields["fault"],
        "status": "closed" if paid else "open",
        "paid": paid,
        "amount_inr": int(fields["amount_inr"]),
        "technician": (fields.get("technician") or "").strip() or None,
        "part_name": (fields.get("part_name") or "").strip() or None,
        "supplier": (fields.get("supplier") or "").strip() or None,
        "warranty_days": int(fields["warranty_days"]) if fields.get("warranty_days") not in (None, "") else None,
        "opened_on": fields.get("opened_on") or date.today().isoformat(),
        "closed_on": closed if paid else None,
    }
    rows = _request("POST", "jobs", body=body)
    return rows[0]


def decisions() -> list[dict]:
    return _request(
        "GET",
        "decisions",
        params={"select": "*", "order": "created_at.desc", "limit": "20"},
    )


def add_decision(row: dict) -> dict:
    rows = _request("POST", "decisions", body=row)
    return rows[0]

"""Dobara counter. Records live in Supabase. Gemma on OpenRouter decides."""

from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import gemma_decide

STATIC = Path(__file__).resolve().parent / "static"


def load_dotenv() -> None:
    path = Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

app = FastAPI(title="Dobara")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class PolicyIn(BaseModel):
    comeback_days: int = Field(ge=0, le=3650)
    labor_inr: int = Field(ge=0)
    touch_quote: int = Field(ge=0)
    battery_quote: int = Field(ge=0)
    charging_quote: int = Field(ge=0)


class TechnicianIn(BaseModel):
    name: str
    skills: list[str]


class CustomerIn(BaseModel):
    name: str
    phone: str
    model: str
    imei: str = ""


class JobIn(BaseModel):
    phone: str
    fault: str
    paid: bool = False
    amount_inr: int = Field(ge=0)
    technician: str = ""
    part_name: str = ""
    supplier: str = ""
    warranty_days: int | None = None
    opened_on: str = ""
    closed_on: str = ""


class ComplaintIn(BaseModel):
    phone: str
    complaint: str


def _phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 10:
        raise HTTPException(status_code=400, detail="Use a 10-digit phone number.")
    return digits


def _guard(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {
        "supabase": db.configured(),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
        "model": gemma_decide.MODEL,
    }


@app.get("/api/config")
def config():
    return {
        "supabaseUrl": os.environ.get("SUPABASE_URL", ""),
        "supabaseAnonKey": os.environ.get("SUPABASE_ANON_KEY", ""),
    }


@app.get("/api/board")
def board():
    try:
        return {
            "policy": db.policy(),
            "technicians": db.technicians(),
            "customers": db.customers(),
            "jobs": db.all_jobs(),
            "decisions": db.decisions(),
        }
    except Exception as exc:
        raise _guard(exc) from exc


@app.post("/api/policy")
def save_policy(body: PolicyIn):
    try:
        return db.save_policy(body.model_dump())
    except Exception as exc:
        raise _guard(exc) from exc


@app.post("/api/technicians")
def add_technician(body: TechnicianIn):
    skills = [skill for skill in body.skills if skill in {"touch", "battery", "charging"}]
    if not body.name.strip() or not skills:
        raise HTTPException(status_code=400, detail="Name and at least one skill are required.")
    try:
        return db.add_technician(body.name, skills)
    except Exception as exc:
        raise _guard(exc) from exc


@app.post("/api/customers")
def add_customer(body: CustomerIn):
    if not body.name.strip() or not body.model.strip():
        raise HTTPException(status_code=400, detail="Name and phone model are required.")
    try:
        return db.add_customer(body.name, _phone(body.phone), body.model, body.imei)
    except Exception as exc:
        raise _guard(exc) from exc


@app.post("/api/jobs")
def add_job(body: JobIn):
    if body.fault not in {"touch", "battery", "charging"}:
        raise HTTPException(status_code=400, detail="Fault must be touch, battery, or charging.")
    phone = _phone(body.phone)
    try:
        customer = db.customer_by_phone(phone)
    except Exception as exc:
        raise _guard(exc) from exc
    if not customer:
        raise HTTPException(status_code=404, detail="No customer has that phone yet.")
    try:
        return db.add_job(
            customer,
            {
                "id": "J-" + uuid.uuid4().hex[:6],
                "fault": body.fault,
                "paid": body.paid,
                "amount_inr": body.amount_inr,
                "technician": body.technician,
                "part_name": body.part_name,
                "supplier": body.supplier,
                "warranty_days": body.warranty_days,
                "opened_on": body.opened_on,
                "closed_on": body.closed_on,
            },
        )
    except Exception as exc:
        raise _guard(exc) from exc


@app.post("/api/decide")
def decide(body: ComplaintIn):
    if not body.complaint.strip():
        raise HTTPException(status_code=400, detail="Type what the customer said.")
    phone = _phone(body.phone)
    try:
        customer = db.customer_by_phone(phone)
        if not customer:
            raise HTTPException(status_code=404, detail="No customer has that phone yet.")
        jobs = db.jobs_for(phone)
        techs = db.technicians()
        shop_policy = db.policy()
        decision = gemma_decide.decide(shop_policy, customer, jobs, techs, body.complaint.strip(), date.today())
        saved = db.add_decision(
            {
                "customer_id": customer["id"],
                "phone": customer["phone"],
                "customer_name": customer["name"],
                "complaint": body.complaint.strip(),
                "fault": decision["fault"],
                "outcome": decision["outcome"],
                "amount_inr": int(decision["amount_inr"]),
                "assignee": decision["assignee"] or None,
                "summary": decision["summary"],
                "based_on": decision["based_on"],
                "model": decision["model"],
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _guard(exc) from exc
    return {"ok": True, "decision": saved}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

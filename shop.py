"""Screenwala's books live in FalkorDB. The outcome is a Cypher CASE."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime

from falkordb import FalkorDB

from parse import parse_complaint

GRAPH_NAME = os.environ.get("DOBARA_GRAPH", "screenwala")
HOST = os.environ.get("FALKORDB_HOST", "localhost")
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))

DECIDE_QUERY = """
MATCH (c:Customer {id: $cid})
MATCH (pol:Policy {id: 'comeback'})
OPTIONAL MATCH (c)-[:OWES]->(unpaid:Job)
OPTIONAL MATCH (utech:Person)-[:DID]->(unpaid)
OPTIONAL MATCH (unpaid)-[:ON]->(udev:Device)
WITH c, pol, unpaid, utech, udev
ORDER BY unpaid.opened_ord DESC
WITH c, pol, head(collect(
  CASE WHEN unpaid IS NULL THEN NULL ELSE {
    id: unpaid.id,
    fault: unpaid.fault,
    amount: unpaid.amount_inr,
    opened_ord: unpaid.opened_ord,
    tech_id: utech.id,
    tech_name: utech.name,
    model: udev.model
  } END
)) AS unpaid
OPTIONAL MATCH (c)<-[:FOR_CUSTOMER]-(j:Job)
WHERE j.paid = true AND j.fault = $fault AND j.closed_ord > 0
OPTIONAL MATCH (tech:Person)-[:DID]->(j)
OPTIONAL MATCH (j)-[:USED]->(p:Part)-[:SUPPLIED_BY]->(s:Supplier)
OPTIONAL MATCH (j)-[:ON]->(d:Device)
WITH c, pol, unpaid, j, tech, p, s, d
ORDER BY j.closed_ord DESC
WITH c, pol, unpaid, head(collect(
  CASE WHEN j IS NULL THEN NULL ELSE {
    id: j.id,
    fault: j.fault,
    amount: j.amount_inr,
    closed_ord: j.closed_ord,
    tech_id: tech.id,
    tech_name: tech.name,
    part: p.name,
    warranty_days: p.warranty_days,
    supplier: s.name,
    model: d.model,
    imei: d.imei
  } END
)) AS last
WITH c, pol, unpaid, last,
  CASE WHEN last IS NULL THEN -1 ELSE $today - last.closed_ord END AS age
RETURN
  c.name AS customer,
  c.phone AS phone,
  pol.comeback_days AS comeback_days,
  pol.labor_inr AS labor_inr,
  unpaid.id AS unpaid_id,
  unpaid.fault AS unpaid_fault,
  unpaid.amount AS unpaid_amount,
  unpaid.opened_ord AS unpaid_opened,
  unpaid.tech_name AS unpaid_tech,
  unpaid.tech_id AS unpaid_tech_id,
  unpaid.model AS unpaid_model,
  last.id AS job_id,
  last.amount AS job_amount,
  last.tech_id AS tech_id,
  last.tech_name AS tech_name,
  last.part AS part,
  last.warranty_days AS warranty_days,
  last.supplier AS supplier,
  last.model AS model,
  last.imei AS imei,
  age AS age_days,
  CASE
    WHEN unpaid IS NOT NULL THEN 'collect_first'
    WHEN last IS NULL THEN 'new_paid'
    WHEN age <= pol.comeback_days THEN 'free_comeback'
    WHEN last.warranty_days IS NOT NULL AND age <= last.warranty_days THEN 'labor_only'
    ELSE 'new_paid'
  END AS outcome
"""

SKILL_QUERY = """
MATCH (p:Person)-[:SKILLED_IN]->(s:Skill {name: $fault})
OPTIONAL MATCH (p)-[:DID]->(open:Job)
WHERE open.status = 'open'
WITH p, s, count(open) AS open_jobs
RETURN p.id AS id, p.name AS name, s.quote_inr AS quote_inr, open_jobs
ORDER BY open_jobs ASC, p.name ASC
LIMIT 1
"""

QUOTE_QUERY = """
MATCH (s:Skill {name: $fault})
RETURN s.quote_inr AS quote_inr
"""


def connect():
    db = FalkorDB(host=HOST, port=PORT)
    return db.select_graph(GRAPH_NAME)


def _rows(result):
    return result.result_set or []


def _today(day: date | None) -> date:
    return day or date.today()


def reset(graph=None, day: date | None = None) -> None:
    graph = graph or connect()
    graph.query("MATCH (n) DETACH DELETE n")
    seed(graph, _today(day))


def ensure_ready(day: date | None = None):
    graph = connect()
    found = _rows(graph.query("MATCH (s:Shop {id: 'screenwala'}) RETURN s.id"))
    if not found:
        seed(graph, _today(day))
    return graph


def seed(graph, today: date) -> None:
    def q(text, params=None):
        graph.query(text, params or {})

    q(
        """
        CREATE (:Shop {id: 'screenwala', name: 'Screenwala', area: 'Karve Nagar, Pune'})
        CREATE (:Policy {id: 'comeback', comeback_days: 30, labor_inr: 400})
        """
    )
    people = [
        ("meera", "Meera Joshi", "owner"),
        ("imran", "Imran Shaikh", "technician"),
        ("sagar", "Sagar Patil", "technician"),
    ]
    for pid, name, role in people:
        q(
            """
            CREATE (p:Person {id: $id, name: $name, role: $role})
            WITH p
            MATCH (s:Shop {id: 'screenwala'})
            CREATE (p)-[:WORKS_AT]->(s)
            """,
            {"id": pid, "name": name, "role": role},
        )
    skills = [("touch", 4500), ("battery", 1800), ("charging", 1200)]
    for name, quote in skills:
        q(
            "CREATE (:Skill {name: $name, quote_inr: $quote})",
            {"name": name, "quote": quote},
        )
    for pid, skill in (
        ("imran", "touch"),
        ("imran", "charging"),
        ("sagar", "battery"),
        ("sagar", "charging"),
    ):
        q(
            """
            MATCH (p:Person {id: $pid}), (s:Skill {name: $skill})
            CREATE (p)-[:SKILLED_IN]->(s)
            """,
            {"pid": pid, "skill": skill},
        )
    q(
        """
        CREATE (:Supplier {id: 'shree', name: 'Shree Displays'})
        CREATE (:Supplier {id: 'cellhouse', name: 'CellHouse'})
        CREATE (:Part {id: 'oled-13', name: 'iPhone 13 display', warranty_days: 90})
        CREATE (:Part {id: 'bn-12', name: 'Redmi Note 12 battery', warranty_days: 60})
        CREATE (:Part {id: 'cp-m14', name: 'Samsung M14 charging port', warranty_days: 30})
        """
    )
    for part, supplier in (
        ("oled-13", "shree"),
        ("bn-12", "cellhouse"),
        ("cp-m14", "cellhouse"),
    ):
        q(
            """
            MATCH (p:Part {id: $part}), (s:Supplier {id: $supplier})
            CREATE (p)-[:SUPPLIED_BY]->(s)
            """,
            {"part": part, "supplier": supplier},
        )
    customers = [
        ("rahul", "Rahul Deshmukh", "9822011100"),
        ("neha", "Neha Kulkarni", "9822022200"),
        ("amit", "Amit Joshi", "9822033300"),
    ]
    for cid, name, phone in customers:
        q(
            "CREATE (:Customer {id: $id, name: $name, phone: $phone})",
            {"id": cid, "name": name, "phone": phone},
        )
    devices = [
        ("d-rahul", "rahul", "356938104412441", "iPhone 13"),
        ("d-neha", "neha", "356938107781778", "Redmi Note 12"),
        ("d-amit", "amit", "356938109991991", "Samsung M14"),
        ("d-wife", "amit", "356938108880880", "Samsung A15"),
    ]
    for did, cid, imei, model in devices:
        q(
            """
            CREATE (d:Device {id: $id, imei: $imei, model: $model})
            WITH d
            MATCH (c:Customer {id: $cid})
            CREATE (c)-[:OWNS]->(d)
            """,
            {"id": did, "imei": imei, "model": model, "cid": cid},
        )

    def job(jid, cid, did, fault, paid, status, amount, opened_ago, closed_ago, tech, part):
        opened = today.toordinal() - opened_ago
        closed = -1 if closed_ago is None else today.toordinal() - closed_ago
        q(
            """
            CREATE (j:Job {
              id: $id, fault: $fault, status: $status, paid: $paid,
              amount_inr: $amount, opened_ord: $opened, closed_ord: $closed
            })
            WITH j
            MATCH (c:Customer {id: $cid})
            MATCH (d:Device {id: $did})
            MATCH (tech:Person {id: $tech})
            CREATE (j)-[:FOR_CUSTOMER]->(c)
            CREATE (j)-[:ON]->(d)
            CREATE (tech)-[:DID]->(j)
            """,
            {
                "id": jid,
                "fault": fault,
                "status": status,
                "paid": paid,
                "amount": amount,
                "opened": opened,
                "closed": closed,
                "cid": cid,
                "did": did,
                "tech": tech,
            },
        )
        if part:
            q(
                """
                MATCH (j:Job {id: $jid}), (p:Part {id: $part})
                CREATE (j)-[:USED]->(p)
                """,
                {"jid": jid, "part": part},
            )
        if not paid:
            q(
                """
                MATCH (c:Customer {id: $cid}), (j:Job {id: $jid})
                CREATE (c)-[:OWES]->(j)
                """,
                {"cid": cid, "jid": jid},
            )

    job("J-104", "rahul", "d-rahul", "touch", True, "closed", 4500, 13, 12, "imran", "oled-13")
    job("J-088", "neha", "d-neha", "battery", True, "closed", 1800, 41, 40, "sagar", "bn-12")
    job("J-091", "amit", "d-amit", "charging", False, "open", 1800, 6, None, "imran", "cp-m14")


def customers(graph) -> list[dict]:
    rows = _rows(graph.query("MATCH (c:Customer) RETURN c.id, c.name, c.phone ORDER BY c.name"))
    return [{"id": row[0], "name": row[1], "phone": row[2]} for row in rows]


def find_customer(graph, parsed: dict) -> dict | None:
    rows = _rows(
        graph.query(
            """
            MATCH (c:Customer)
            WHERE ($phone <> '' AND c.phone = $phone)
               OR ($name <> '' AND toLower(c.name) CONTAINS toLower($name))
            RETURN c.id, c.name, c.phone
            """,
            {"phone": parsed.get("phone") or "", "name": parsed.get("name") or ""},
        )
    )
    if not rows:
        return None
    phone = parsed.get("phone") or ""
    for row in rows:
        if phone and row[2] == phone:
            return {"id": row[0], "name": row[1], "phone": row[2]}
    return {"id": rows[0][0], "name": rows[0][1], "phone": rows[0][2]}


def _as_dict(row) -> dict:
    keys = [
        "customer",
        "phone",
        "comeback_days",
        "labor_inr",
        "unpaid_id",
        "unpaid_fault",
        "unpaid_amount",
        "unpaid_opened",
        "unpaid_tech",
        "unpaid_tech_id",
        "unpaid_model",
        "job_id",
        "job_amount",
        "tech_id",
        "tech_name",
        "part",
        "warranty_days",
        "supplier",
        "model",
        "imei",
        "age_days",
        "outcome",
    ]
    return dict(zip(keys, row))


def _rupees(amount) -> str:
    if amount is None:
        return "Rs 0"
    return f"Rs {int(amount):,}"


def _summary(row: dict, fault: str, quote: int | None, assignee: str | None) -> str:
    outcome = row["outcome"]
    name = row["customer"]
    if outcome == "collect_first":
        return (
            f"Do not open a new job for {name}. "
            f"{row['unpaid_id']} is still unpaid: {row['unpaid_fault']} on the "
            f"{row['unpaid_model']} for {_rupees(row['unpaid_amount'])}, "
            f"with {row['unpaid_tech']}. Collect that before any new work."
        )
    if outcome == "free_comeback":
        return (
            f"Free comeback for {name}. The {row['model']} {fault} was repaired "
            f"{int(row['age_days'])} days ago on {row['job_id']} by {row['tech_name']}, "
            f"inside the {int(row['comeback_days'])}-day promise. "
            f"{row['part']} came from {row['supplier']}. "
            f"Assign {assignee}. Charge Rs 0."
        )
    if outcome == "labor_only":
        left = int(row["warranty_days"]) - int(row["age_days"])
        return (
            f"Charge labor only, {_rupees(row['labor_inr'])}. "
            f"{name}'s {row['model']} {fault} was repaired {int(row['age_days'])} days ago, "
            f"past the {int(row['comeback_days'])}-day promise. "
            f"{row['part']} from {row['supplier']} is still inside its "
            f"{int(row['warranty_days'])}-day warranty, with {left} days left. "
            f"Assign {assignee}."
        )
    return (
        f"New paid job for {name}. No closed {fault} repair sits inside the shop promise "
        f"or a part warranty. Quote {_rupees(quote)}. Assign {assignee}."
    )


def _path(row: dict, fault: str, due_age: int | None) -> list[dict]:
    steps = [
        {"kind": "Customer", "label": row["customer"], "detail": row["phone"]},
    ]
    if row["outcome"] == "collect_first":
        steps.append(
            {
                "kind": "Unpaid job",
                "label": f"{row['unpaid_id']} · {row['unpaid_fault']}",
                "detail": f"{row['unpaid_model']} · {_rupees(row['unpaid_amount'])} · {due_age} days open · {row['unpaid_tech']}",
            }
        )
        steps.append(
            {
                "kind": "Policy",
                "label": "Collect before new work",
                "detail": "An open due blocks the next job",
            }
        )
        return steps
    if row["job_id"]:
        steps.append(
            {
                "kind": "Device",
                "label": row["model"],
                "detail": f"IMEI {row['imei']}",
            }
        )
        steps.append(
            {
                "kind": "Earlier job",
                "label": f"{row['job_id']} · {fault}",
                "detail": f"closed {int(row['age_days'])} days ago · paid {_rupees(row['job_amount'])} · {row['tech_name']}",
            }
        )
        if row["part"]:
            left = int(row["warranty_days"]) - int(row["age_days"])
            steps.append(
                {
                    "kind": "Part",
                    "label": row["part"],
                    "detail": f"{row['supplier']} · {int(row['warranty_days'])}-day warranty · {left} days left",
                }
            )
    steps.append(
        {
            "kind": "Policy",
            "label": f"{int(row['comeback_days'])}-day comeback",
            "detail": (
                f"{int(row['age_days'])} days since the matching repair"
                if row["job_id"]
                else "No matching closed repair"
            ),
        }
    )
    return steps


def _record(graph, row: dict, complaint: str, fault: str, summary: str, amount: int, assignee_id: str | None, today: date) -> str:
    decision_id = "D-" + uuid.uuid4().hex[:8]
    graph.query(
        """
        CREATE (dec:Decision {
          id: $id, outcome: $outcome, summary: $summary, complaint: $complaint,
          fault: $fault, at: $at, at_ord: $at_ord, amount_inr: $amount
        })
        WITH dec
        MATCH (c:Customer {phone: $phone})
        MATCH (pol:Policy {id: 'comeback'})
        CREATE (dec)-[:ABOUT]->(c)
        CREATE (dec)-[:UNDER]->(pol)
        """,
        {
            "id": decision_id,
            "outcome": row["outcome"],
            "summary": summary,
            "complaint": complaint,
            "fault": fault,
            "at": datetime.now().isoformat(timespec="seconds"),
            "at_ord": today.toordinal(),
            "amount": amount,
            "phone": row["phone"],
        },
    )
    evidence = [job_id for job_id in (row["unpaid_id"], row["job_id"]) if job_id]
    for job_id in evidence:
        graph.query(
            """
            MATCH (dec:Decision {id: $id}), (j:Job {id: $job})
            CREATE (dec)-[:BASED_ON]->(j)
            """,
            {"id": decision_id, "job": job_id},
        )
    if assignee_id:
        graph.query(
            """
            MATCH (dec:Decision {id: $id}), (p:Person {id: $tech})
            CREATE (dec)-[:ASSIGNED_TO]->(p)
            """,
            {"id": decision_id, "tech": assignee_id},
        )
    return decision_id


def decide(complaint: str, graph=None, day: date | None = None) -> dict:
    graph = graph or connect()
    today = _today(day)
    parsed = parse_complaint(complaint, customers(graph))
    if not parsed["fault"]:
        return {
            "ok": False,
            "error": "Say whether it is the touch, the battery, or the charging port.",
            "parsed": parsed,
        }
    customer = find_customer(graph, parsed)
    if not customer:
        return {
            "ok": False,
            "error": "No customer in the book matches that name or phone.",
            "parsed": parsed,
        }
    found = _rows(
        graph.query(
            DECIDE_QUERY,
            {"cid": customer["id"], "fault": parsed["fault"], "today": today.toordinal()},
        )
    )
    if not found:
        return {"ok": False, "error": "The graph returned no row for that customer.", "parsed": parsed}
    row = _as_dict(found[0])
    quote_row = _rows(graph.query(QUOTE_QUERY, {"fault": parsed["fault"]}))
    quote = int(quote_row[0][0]) if quote_row else 0
    assignee_id = None
    assignee = None
    if row["outcome"] == "collect_first":
        amount = int(row["unpaid_amount"] or 0)
    elif row["outcome"] == "free_comeback":
        amount = 0
        assignee_id = row["tech_id"]
        assignee = row["tech_name"]
    elif row["outcome"] == "labor_only":
        amount = int(row["labor_inr"] or 0)
        assignee_id = row["tech_id"]
        assignee = row["tech_name"]
    else:
        skill = _rows(graph.query(SKILL_QUERY, {"fault": parsed["fault"]}))
        if skill:
            assignee_id, assignee, quote = skill[0][0], skill[0][1], int(skill[0][2])
        amount = quote
    due_age = None
    if row["unpaid_opened"]:
        due_age = today.toordinal() - int(row["unpaid_opened"])
        row["age_days"] = due_age if row["outcome"] == "collect_first" else row["age_days"]
    summary = _summary(row, parsed["fault"], quote, assignee)
    if row["outcome"] == "collect_first" and due_age is not None:
        summary = (
            f"Do not open a new job for {row['customer']}. "
            f"{row['unpaid_id']} is still unpaid: {row['unpaid_fault']} on the "
            f"{row['unpaid_model']} for {_rupees(row['unpaid_amount'])}, "
            f"open {due_age} days, with {row['unpaid_tech']}. Collect that before any new work."
        )
    decision_id = _record(
        graph, row, complaint.strip(), parsed["fault"], summary, amount, assignee_id, today
    )
    return {
        "ok": True,
        "decision_id": decision_id,
        "outcome": row["outcome"],
        "summary": summary,
        "amount_inr": amount,
        "assignee": assignee,
        "fault": parsed["fault"],
        "customer": {"name": row["customer"], "phone": row["phone"]},
        "path": _path(row, parsed["fault"], due_age),
        "parsed": parsed,
        "cypher": DECIDE_QUERY.strip(),
    }


def remember(question: str, graph=None) -> list[dict]:
    graph = graph or connect()
    needle = question.strip()
    for prefix in ("what did we decide about ", "what did we decide for "):
        if needle.lower().startswith(prefix):
            needle = needle[len(prefix) :]
    needle = needle.strip(" ?.!")
    rows = _rows(
        graph.query(
            """
            MATCH (dec:Decision)-[:ABOUT]->(c:Customer)
            WHERE toLower(c.name) CONTAINS toLower($q)
               OR c.phone CONTAINS $q
               OR toLower(dec.complaint) CONTAINS toLower($q)
            OPTIONAL MATCH (dec)-[:BASED_ON]->(j:Job)
            OPTIONAL MATCH (dec)-[:ASSIGNED_TO]->(p:Person)
            RETURN dec.id, dec.outcome, dec.summary, dec.complaint, dec.at,
                   dec.amount_inr, c.name, c.phone,
                   collect(DISTINCT j.id), p.name
            ORDER BY dec.at DESC
            """,
            {"q": needle},
        )
    )
    memories = []
    for row in rows:
        memories.append(
            {
                "id": row[0],
                "outcome": row[1],
                "summary": row[2],
                "complaint": row[3],
                "at": row[4],
                "amount_inr": row[5],
                "customer": row[6],
                "phone": row[7],
                "based_on": [job for job in (row[8] or []) if job],
                "assignee": row[9],
            }
        )
    return memories


def board(graph=None) -> dict:
    graph = graph or connect()
    people = _rows(
        graph.query(
            """
            MATCH (p:Person)-[:WORKS_AT]->(:Shop {id: 'screenwala'})
            OPTIONAL MATCH (p)-[:SKILLED_IN]->(s:Skill)
            RETURN p.name, p.role, collect(DISTINCT s.name)
            ORDER BY p.role DESC, p.name
            """
        )
    )
    dues = _rows(
        graph.query(
            """
            MATCH (c:Customer)-[:OWES]->(j:Job)
            MATCH (j)-[:ON]->(d:Device)
            OPTIONAL MATCH (tech:Person)-[:DID]->(j)
            RETURN c.name, c.phone, j.id, j.fault, j.amount_inr, d.model, tech.name
            ORDER BY c.name
            """
        )
    )
    decisions = _rows(
        graph.query(
            """
            MATCH (dec:Decision)-[:ABOUT]->(c:Customer)
            OPTIONAL MATCH (dec)-[:ASSIGNED_TO]->(p:Person)
            RETURN dec.id, dec.outcome, dec.summary, dec.at, dec.amount_inr,
                   c.name, p.name
            ORDER BY dec.at DESC
            """
        )
    )
    return {
        "shop": "Screenwala",
        "area": "Karve Nagar, Pune",
        "people": [
            {"name": row[0], "role": row[1], "skills": [s for s in (row[2] or []) if s]}
            for row in people
        ],
        "dues": [
            {
                "customer": row[0],
                "phone": row[1],
                "job": row[2],
                "fault": row[3],
                "amount_inr": row[4],
                "model": row[5],
                "tech": row[6],
            }
            for row in dues
        ],
        "decisions": [
            {
                "id": row[0],
                "outcome": row[1],
                "summary": row[2],
                "at": row[3],
                "amount_inr": row[4],
                "customer": row[5],
                "assignee": row[6],
            }
            for row in decisions
        ],
    }

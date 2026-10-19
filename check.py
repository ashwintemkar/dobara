"""Checks Gemma's decision against live-shaped rows. No network."""

from gemma_decide import validate

jobs = [
    {
        "id": "J-104",
        "fault": "touch",
        "status": "closed",
        "paid": True,
        "amount_inr": 4500,
        "technician": "Imran Shaikh",
    },
    {
        "id": "J-091",
        "fault": "charging",
        "status": "open",
        "paid": False,
        "amount_inr": 1800,
        "technician": "Imran Shaikh",
    },
]
techs = [{"name": "Imran Shaikh", "skills": ["touch", "charging"]}]

ok = {
    "fault": "touch",
    "outcome": "collect_first",
    "amount_inr": 1800,
    "assignee": "",
    "based_on": ["J-091"],
    "summary": "Collect J-091 before any new work.",
}
assert validate(ok, jobs, techs) is None

invented = dict(ok, based_on=["J-nope"])
assert validate(invented, jobs, techs)

skipped = dict(ok, outcome="free_comeback", based_on=["J-104"])
assert "unpaid" in validate(skipped, jobs, techs)

stranger = dict(ok, assignee="Nobody")
assert "floor" in validate(stranger, jobs, techs)

print("ok")

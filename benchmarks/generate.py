"""Deterministic, realistic benchmark payloads. Re-run to regenerate benchmarks/payloads/*.

Each generator plants "needles": facts a downstream task must still be able to answer after compression.
run.py measures token savings per stage and needle recall, which is the Phase 0 success gate.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "payloads"

FIRST = [
    "Ada",
    "Grace",
    "Linus",
    "Margaret",
    "Dennis",
    "Barbara",
    "Ken",
    "Radia",
    "Guido",
    "Anita",
    "Tim",
    "Hedy",
    "Alan",
    "Frances",
    "Edsger",
    "Katherine",
]
LAST = [
    "Lovelace",
    "Hopper",
    "Torvalds",
    "Hamilton",
    "Ritchie",
    "Liskov",
    "Thompson",
    "Perlman",
    "van Rossum",
    "Borg",
    "Berners-Lee",
    "Lamarr",
    "Turing",
    "Allen",
    "Dijkstra",
    "Johnson",
]
CITIES = ["Berlin", "Pune", "Austin", "Lisbon", "Toronto", "Nairobi", "Osaka", "Bogotá", "Oslo", "Dublin"]
PRODUCTS = [
    "Mechanical keyboard",
    "USB-C dock",
    "27in monitor",
    "Noise-cancelling headset",
    "Standing desk mat",
    "Webcam 4K",
    "Laptop stand",
    "Thunderbolt cable",
    "Ergonomic mouse",
    "Desk lamp",
]
STATUSES = ["shipped", "processing", "delivered", "cancelled", "returned"]
CARRIERS = ["DHL", "FedEx", "UPS", "BlueDart", "DPD"]


def orders(rng: random.Random, n: int = 200) -> tuple[list[dict], dict]:
    rows = []
    for i in range(n):
        f, last = rng.choice(FIRST), rng.choice(LAST)
        status = rng.choice(STATUSES)
        rows.append(
            {
                "order_id": f"ORD-{10000 + i}",
                "customer": {
                    "name": f"{f} {last}",
                    "email": f"{f.lower()}.{last.lower().replace(' ', '')}@example.com",
                    "tier": rng.choice(["free", "pro", "enterprise"]),
                },
                "items": [
                    {
                        "sku": f"SKU-{rng.randint(100, 999)}",
                        "name": rng.choice(PRODUCTS),
                        "qty": rng.randint(1, 4),
                        "unit_price": round(rng.uniform(9, 499), 2),
                    }
                    for _ in range(rng.randint(1, 3))
                ],
                "total_usd": None,
                "currency": "USD",
                "status": status,
                "shipping": {
                    "city": rng.choice(CITIES),
                    "carrier": rng.choice(CARRIERS) if status in ("shipped", "delivered") else None,
                    "tracking": f"TRK{rng.randint(10**9, 10**10 - 1)}" if status in ("shipped", "delivered") else None,
                },
                "notes": "" if rng.random() < 0.7 else rng.choice(["Gift wrap requested", "Leave at reception", "Call before delivery"]),
                "tags": [] if rng.random() < 0.6 else ["priority"],
                "created_at": f"2026-08-{rng.randint(1, 28):02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z",
                "updated_at": None,
                "internal_ref": None,
            }
        )
        rows[-1]["total_usd"] = round(sum(it["qty"] * it["unit_price"] for it in rows[-1]["items"]), 2)
    # needles: three orders for Ada Lovelace shipped to Berlin
    needles = []
    for j, idx in enumerate([17, 88, 143]):
        rows[idx]["customer"] = {"name": "Ada Lovelace", "email": "ada.lovelace@example.com", "tier": "enterprise"}
        rows[idx]["status"] = "shipped"
        rows[idx]["shipping"] = {"city": "Berlin", "carrier": "DHL", "tracking": f"TRK77700000{j}"}
        needles.append(rows[idx]["order_id"])
    return rows, {
        "query": "orders for Ada Lovelace shipped to Berlin",
        "needles": needles,
        "top_k": 12,
        "flatten": True,
        "question": "Which order ids belong to Ada Lovelace's Berlin shipments and what are their tracking numbers?",
    }


def chat(rng: random.Random, turns: int = 60) -> tuple[dict, dict]:
    msgs = [
        {
            "role": "system",
            "content": "You are Acme's support assistant. Be concise. Never share internal ticket ids with customers. Escalate refunds over $500 to a human.",
        }
    ]
    topics = [
        "password reset",
        "invoice download",
        "changing the billing email",
        "API rate limits",
        "SSO setup",
        "exporting data",
        "dark mode",
        "mobile app crash",
        "webhook retries",
        "seat pricing",
    ]
    for _i in range(turns):
        t = rng.choice(topics)
        msgs.append(
            {
                "role": "user",
                "content": f"Hi, I have a question about {t}. {rng.choice(['It is not working as I expected.', 'Where do I find it?', 'Is this available on the free plan?', 'It worked yesterday.'])}",
                "name": None,
            }
        )
        msgs.append(
            {
                "role": "assistant",
                "content": f"Sure. For {t}, go to Settings and look for the {t.split()[0].capitalize()} section. {rng.choice(['Let me know if that helps.', 'You can also check our docs.', 'Happy to walk you through it.'])}",
                "tool_calls": None,
            }
        )
    # needle: earlier in the conversation the user gave their order number and the promised refund amount
    msgs[9] = {
        "role": "user",
        "content": "Also my order number is ORD-55213 and I was promised a refund of $640 for the damaged monitor.",
        "name": None,
    }
    msgs[10] = {
        "role": "assistant",
        "content": "Thanks. I have noted order ORD-55213 and the $640 refund. Since it is above $500 I am escalating to a human agent; you will hear back within 24 hours.",
        "tool_calls": None,
    }
    msgs.append({"role": "user", "content": "Any update on my refund? What was the amount again and which order was it?", "name": None})
    return {"model": "gpt-4o", "messages": msgs, "temperature": 0.2, "metadata": {"session": "abc123", "debug": None}}, {
        "query": "refund amount order number damaged monitor",
        "needles": ["ORD-55213", "640"],
        "keep_last": 6,
        "top_k": 12,
        "question": "What refund amount was promised and for which order?",
    }


def rag_chunks(rng: random.Random, n: int = 40) -> tuple[list[dict], dict]:
    filler = [
        "The quarterly review covers hiring plans, office moves and the updated travel policy for all regions.",
        "Our data retention policy keeps application logs for 30 days and audit logs for one year unless legal hold applies.",
        "Kubernetes upgrades are performed monthly during the Sunday maintenance window with a canary cluster first.",
        "The design system ships tokens for color, spacing and typography; components consume them through CSS variables.",
        "Expense reports must be filed within 30 days of travel and require receipts above 25 USD.",
        "On-call rotations are weekly; the primary is paged first and the secondary after five minutes without acknowledgement.",
        "The mobile team is migrating from React Native 0.72 to 0.76 and expects the work to finish next quarter.",
        "Customer data is encrypted at rest with AES-256 and in transit with TLS 1.3 across every service.",
    ]
    chunks = []
    for i in range(n):
        chunks.append(
            {
                "id": f"doc-{i:03d}",
                "source": rng.choice(["handbook.pdf", "runbook.md", "policy.docx", "faq.md"]),
                "page": rng.randint(1, 40),
                "score": round(rng.uniform(0.2, 0.9), 3),
                "text": rng.choice(filler) + " " + rng.choice(filler),
                "metadata": {"author": rng.choice(FIRST), "updated": f"2026-0{rng.randint(1, 8)}-1{rng.randint(0, 9)}", "tags": []},
            }
        )
    chunks[7]["text"] = (
        "Incident postmortems must be published within 5 business days. The severity-1 SLA for initial response is 15 minutes, and the status page must be updated every 30 minutes until resolution."
    )
    chunks[23]["text"] = (
        "For severity-1 incidents the incident commander is the on-call SRE lead; the communications lead posts customer updates to the status page every 30 minutes."
    )
    return chunks, {
        "query": "severity-1 incident response SLA status page update frequency",
        "needles": ["15 minutes", "30 minutes", "doc-007"],
        "top_k": 5,
        "question": "What is the sev-1 initial response SLA and how often is the status page updated?",
    }


def api_object(rng: random.Random) -> tuple[dict, dict]:
    def user(i):
        f, last = rng.choice(FIRST), rng.choice(LAST)
        return {
            "id": 5000 + i,
            "login": f"{f.lower()}{last.lower()[:3]}",
            "name": f"{f} {last}",
            "email": f"{f.lower()}@example.com",
            "avatar_url": f"https://avatars.example.com/u/{5000 + i}?v=4",
            "html_url": f"https://example.com/{f.lower()}",
            "type": "User",
            "site_admin": False,
            "company": rng.choice([None, "Acme", "Globex", ""]),
            "blog": "",
            "location": rng.choice(CITIES + [None]),
            "bio": None,
            "twitter_username": None,
            "public_repos": rng.randint(0, 120),
            "followers": rng.randint(0, 900),
            "following": rng.randint(0, 300),
            "created_at": f"20{rng.randint(10, 25)}-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}T10:00:00Z",
            "updated_at": f"2026-08-{rng.randint(1, 28):02d}T10:00:00Z",
            "plan": {"name": rng.choice(["free", "pro"]), "space": 976562499, "collaborators": 0, "private_repos": rng.randint(0, 50)},
            "permissions": {"admin": False, "push": True, "pull": True},
            "node_id": f"MDQ6VXNlcj{5000 + i}==",
        }

    members = [user(i) for i in range(35)]
    members[12]["name"] = "Radia Perlman"
    members[12]["login"] = "radia"
    members[12]["public_repos"] = 42
    members[12]["location"] = "Toronto"
    return {
        "organization": {"login": "acme", "id": 42, "description": "", "public_members_count": 35, "billing_email": None},
        "members": members,
        "pagination": {"next": None, "prev": None, "per_page": 100},
    }, {
        "query": None,
        "needles": ["radia", "42", "Toronto"],
        "top_k": None,
        "drop_fields": ["*_url", "node_id", "site_admin", "type", "permissions", "plan"],
        "flatten": True,
        "question": "How many public repos does the member named Radia Perlman have and where is she located?",
    }


def logs(rng: random.Random, n: int = 400) -> tuple[list[dict], dict]:
    services = ["payment-service", "checkout-api", "auth", "search", "notifications"]
    rows = []
    for i in range(n):
        lvl = rng.choices(["INFO", "WARN", "ERROR"], weights=[80, 15, 5])[0]
        svc = rng.choice(services)
        rows.append(
            {
                "ts": f"2026-09-08T10:{i // 60:02d}:{i % 60:02d}.{rng.randint(0, 999):03d}Z",
                "level": lvl,
                "service": svc,
                "trace_id": f"{rng.getrandbits(64):016x}",
                "span_id": f"{rng.getrandbits(32):08x}",
                "msg": rng.choice(["request completed", "cache hit", "cache miss", "db query", "retrying upstream", "slow response"])
                if lvl != "ERROR"
                else rng.choice(["upstream 502", "db connection reset", "validation failed"]),
                "latency_ms": rng.randint(3, 900),
                "status": 200 if lvl == "INFO" else rng.choice([500, 502, 504, 429]),
                "user_id": None,
                "extra": {},
            }
        )
    for idx in (133, 271, 388):
        rows[idx].update(
            {
                "level": "ERROR",
                "service": "payment-service",
                "msg": "timeout calling gateway after 30000ms",
                "status": 504,
                "latency_ms": 30000,
                "trace_id": f"deadbeef{idx:08x}",
            }
        )
    return rows, {
        "query": "payment-service timeout gateway error",
        "needles": ["deadbeef00000085", "deadbeef0000010f", "deadbeef00000184", "30000"],
        "top_k": 8,
        "question": "Which trace ids show the payment gateway timeouts and how long did they wait?",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(1706)
    cases = {"orders": orders(rng), "chat": chat(rng), "rag_chunks": rag_chunks(rng), "api_object": api_object(rng), "logs": logs(rng)}
    manifest = {}
    for name, (data, spec) in cases.items():
        if name == "logs":
            (OUT / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in data) + "\n")
            spec["file"] = f"{name}.jsonl"
        else:
            (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            spec["file"] = f"{name}.json"
        manifest[name] = spec
    (OUT / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(cases)} payloads to {OUT}")


if __name__ == "__main__":
    main()

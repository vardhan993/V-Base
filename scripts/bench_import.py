"""One-off benchmark: import a large CSV through the real API and time each step.

Run:  .venv/Scripts/python.exe scripts/bench_import.py [rows]
Uses the local dev Postgres (vbase-pg on :5433). Writes a summary to stdout.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

# Same environment contract as tests/backend/conftest.py, minus pytest.
TEST_DATABASE_URL = os.environ.get(
    "VBASE_TEST_DATABASE_URL",
    "postgresql+asyncpg://vbase:vbase_dev_pw@127.0.0.1:5433/vbase_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "bench-only-secret-key-0123456789abcdef"
os.environ["FRONTEND_URL"] = "http://localhost:5173"
os.environ["DB_POOL_SIZE"] = "5"
os.environ["DB_MAX_OVERFLOW"] = "5"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "500"
os.environ["RATE_LIMIT_WRITE_PER_MINUTE"] = "10000"
os.environ["SEQUENCES_POLL_ENABLED"] = "false"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "src"))

import csv
import tempfile

TMP = Path(tempfile.mkdtemp(prefix="vbase-bench-"))
os.environ["UPLOADS_DIR"] = str(TMP / "uploads")
os.environ["BACKUPS_DIR"] = str(TMP / "backups")

ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000


def generate_csv(path: Path, rows: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Full Name", "Email Address", "Company", "Job Title", "City", "LinkedIn", "Phone"])
        for i in range(rows):
            w.writerow([
                f"Person {i}",
                f"person{i}@bench-testing.io",
                f"Bench Corp {i % 500}",
                "Analyst",
                "Mumbai",
                "https://linkedin.com/in/bench-" + str(i),
                "+91 98" + f"{200000000 + i:09d}",
            ])


def reset_db() -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from nexus.core.db import build_connect_args

    url, connect_args = build_connect_args(TEST_DATABASE_URL)

    import asyncio

    async def drop_and_create() -> None:
        engine = create_async_engine(url, connect_args=connect_args, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        finally:
            await engine.dispose()

    asyncio.run(drop_and_create())
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "src/nexus/migrations"))
    command.upgrade(config, "head")


async def main() -> None:
    import httpx

    from nexus.app import app

    csv_path = TMP / "bench_import.csv"
    t0 = time.perf_counter()
    generate_csv(csv_path, ROWS)
    print(f"[gen] {ROWS} rows in {time.perf_counter() - t0:.2f}s -> {csv_path}")

    origin = "http://localhost:5173"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=origin) as client:
        email = f"bench_{uuid.uuid4().hex[:8]}@example.com"
        headers = {"Origin": origin, "X-CSRF-Token": "bench-csrf"}
        r = await client.post(
            "/api/v1/auth/signup",
            json={"email": email, "username": email.split("@")[0], "password": "Str0ngPassw0rd!", "full_name": "Bench"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        headers["X-CSRF-Token"] = client.cookies.get("vbase_csrf")

        t0 = time.perf_counter()
        with csv_path.open("rb") as f:
            r = await client.post(
                "/api/v1/import/upload", files={"file": ("bench_import.csv", f, "text/csv")}, headers=headers
            )
        assert r.status_code == 201, r.text
        job_id = r.json()["job_id"]
        print(f"[upload] {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        r = await client.get(f"/api/v1/import/preview/{job_id}", headers=headers)
        assert r.status_code == 200, r.text
        print(f"[preview] {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/import/mapping/{job_id}",
            json={"mapping": {
                "Full Name": "full_name",
                "Email Address": "email",
                "Company": "company_name",
                "Job Title": "job_title",
                "City": "city",
                "LinkedIn": "linkedin_url",
                "Phone": "phone",
            }},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        print(f"[mapping] {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        r = await client.get("/api/v1/import/plan/" + str(job_id), headers=headers, params={"limit": 50})
        assert r.status_code == 200, r.text
        plan = r.json()
        plan_time = time.perf_counter() - t0
        print(f"[PLAN/dry-run] {plan_time:.2f}s rows_total={plan['rows_total']} counts={plan['counts']}")

        t0 = time.perf_counter()
        r = await client.post("/api/v1/import/run/" + str(job_id), headers=headers)
        assert r.status_code == 200, r.text
        run = r.json()
        run_time = time.perf_counter() - t0
        keys = ("rows_added", "rows_skipped", "rows_invalid", "rows_processed")
        summary = {k: run.get(k) for k in keys}
        print(f"[RUN] {run_time:.2f}s summary={summary}")

        # Re-plan after the import: everything should be 'unchanged' now (still fast).
        t0 = time.perf_counter()
        r = await client.get("/api/v1/import/plan/" + str(job_id), headers=headers)
        assert r.status_code == 200, r.text
        post = r.json()
        print(f"[re-plan] {time.perf_counter() - t0:.2f}s counts={post['counts']}")

    print("PLAN_TIME_S=%.2f" % plan_time)
    print("RUN_TIME_S=%.2f" % run_time)


if __name__ == "__main__":
    import asyncio

    reset_db()
    if os.environ.get("BENCH_PROFILE"):
        import cProfile
        import pstats

        async def _profiled():
            pass

        pr = cProfile.Profile()
        pr.enable()
        asyncio.run(main())
        pr.disable()
        pstats.Stats(pr).sort_stats("cumulative").print_stats(30)
        pstats.Stats(pr).sort_stats("tottime").print_stats("nexus", 25)
    else:
        asyncio.run(main())

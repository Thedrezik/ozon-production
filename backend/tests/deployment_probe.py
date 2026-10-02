"""Measured PostgreSQL plans/concurrency, strictly inside generated E2E projects."""
import json
import os
import re
import resource
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

from fastapi.testclient import TestClient
from sqlalchemy import event, inspect

from app.config import Settings
from app.main import create_app
from app.models import utc_now


def main():
    settings = Settings()
    if (settings.app_env != "test" or not settings.ozon_mock_mode
            or not re.fullmatch(r"ozon-e2e-[a-f0-9]+", os.environ.get("E2E_PROJECT", ""))
            or not settings.database_url.startswith("postgresql+psycopg://")):
        raise RuntimeError("Probe requires generated synthetic PostgreSQL E2E environment")
    app = create_app(settings)
    date = utc_now().date().isoformat()
    paths = ["/api/orders", "/api/dashboard", "/api/money-at-risk",
             f"/api/analytics?start={date}&end={date}", "/api/audit"]
    report = {"requests": [], "plans": [], "indexes": {}, "concurrency": {}}
    inspector = inspect(app.state.engine)
    for table in ("orders", "audit_log", "notifications", "notification_deliveries", "status_history"):
        report["indexes"][table] = [row["name"] for row in inspector.get_indexes(table)]
    with app.state.engine.connect() as connection:
        report["migration"] = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        report["pg_connections_before"] = connection.exec_driver_sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()").scalar_one()
        connection.exec_driver_sql("ANALYZE")
        connection.commit()
    # No lifespan: avoid starting a second scheduler. Ordinary routes/SQL/RBAC.
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": "admin", "password": "e2e-admin-password"}).status_code == 200
    seen = set()
    for path in paths:
        queries = []

        def record(_conn, _cursor, statement, parameters, _context, many, queries=queries):
            if not many and statement.lstrip().upper().startswith("SELECT"):
                queries.append((statement, parameters))

        event.listen(app.state.engine, "before_cursor_execute", record)
        started = time.perf_counter()
        try:
            response = client.get(path)
            assert response.status_code == 200
        finally:
            event.remove(app.state.engine, "before_cursor_execute", record)
        report["requests"].append({"path": path, "seconds": time.perf_counter() - started, "selects": len(queries)})
        with app.state.engine.connect() as connection:
            for sql, parameters in queries:
                # Do not retain auth queries, tokens, passwords or SQL parameters.
                if sql in seen or not any(f"FROM {table}" in sql for table in ("orders", "audit_log", "order_items", "assignments", "status_history")):
                    continue
                seen.add(sql)
                plan = connection.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, parameters).scalar_one()
                report["plans"].append({"path": path, "plan": plan})
    client.close()

    def parallel_read(index):
        opener = build_opener(HTTPCookieProcessor())
        login = Request("http://127.0.0.1:8000/api/auth/login", data=json.dumps({"username": "admin", "password": "e2e-admin-password"}).encode(), headers={"Content-Type": "application/json"})
        with opener.open(login, timeout=15) as response:
            assert response.status == 200
        started = time.perf_counter()
        for path in paths:
            with opener.open("http://127.0.0.1:8000" + path, timeout=30) as response:
                assert response.status == 200
                response.read()
        return time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=4) as pool:
        samples = list(pool.map(parallel_read, range(4)))
    report["concurrency"] = {"clients": 4, "request_count": 20, "client_seconds": samples,
                             "median_client_seconds": statistics.median(samples)}
    with app.state.engine.connect() as connection:
        report["pg_connections_after"] = connection.exec_driver_sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()").scalar_one()
        report["idle_in_transaction"] = connection.exec_driver_sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction'").scalar_one()
    report["probe_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    app.state.engine.dispose()
    Path("/e2e/postgres-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: PostgreSQL migrations/index inventory, actual query EXPLAIN ANALYZE, five API reads and four parallel clients; report is synthetic.")


if __name__ == "__main__":
    main()

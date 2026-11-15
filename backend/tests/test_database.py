from sqlalchemy import create_engine, inspect, text

import app.database as dbm


def test_old_database_schema_is_migrated(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE security_audit_logs (id INTEGER PRIMARY KEY, prompt TEXT NOT NULL, risk_score FLOAT NOT NULL, decision VARCHAR(20) NOT NULL, justification TEXT NOT NULL, timestamp DATETIME)"))
    monkeypatch.setattr(dbm, "engine", eng)
    dbm.init_db()
    cols = {c["name"] for c in inspect(eng).get_columns("security_audit_logs")}
    assert {"thread_id", "user_id", "role", "resolved_by", "latency_ms", "status"} <= cols


def test_init_db_is_idempotent_and_creates_indexes(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/new.db")
    monkeypatch.setattr(dbm, "engine", eng)
    dbm.init_db()
    dbm.init_db()
    indexed = {tuple(i["column_names"]) for i in inspect(eng).get_indexes("security_audit_logs")}
    assert ("decision",) in indexed and ("thread_id", "id") in indexed

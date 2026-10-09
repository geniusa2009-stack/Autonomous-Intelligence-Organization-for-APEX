from sqlalchemy import inspect

from apex_one.persistence.db import db_ready, get_engine, init_db, session_scope
from apex_one.persistence.models import JobRow


def test_migrations_run_and_tables_exist():
    init_db()
    assert db_ready()
    tables = set(inspect(get_engine()).get_table_names())
    for t in ("jobs", "claims", "fact_locks", "kg_nodes", "kg_edges", "memory_semantic", "memory_episodic",
              "memory_evidence", "memory_design", "memory_voice", "memory_failure", "memory_approval",
              "preference_pairs", "provider_attestations", "price_checks", "license_verifications"):
        assert t in tables, t


def test_session_roundtrip():
    init_db()
    with session_scope() as s:
        s.add(JobRow(job_id="J-1", status="PENDING", state="NEW", opportunity_name="x", quality_mode="ultra",
                     payload={"a": 1}))
    with session_scope() as s:
        assert s.get(JobRow, "J-1").payload == {"a": 1}

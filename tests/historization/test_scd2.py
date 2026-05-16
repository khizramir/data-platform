from datetime import datetime, timezone, timedelta

from data_platform.historization.scd2 import SCD2Manager, UpsertAction


def test_scd2_insert_and_update():
    m = SCD2Manager(natural_key_fields=["id"]) 
    ts1 = datetime(2020,1,1, tzinfo=timezone.utc)
    r1 = {"id": 1, "name": "Alice", "val": 10}
    res1 = m.upsert(r1, timestamp=ts1)
    assert res1.action == UpsertAction.INSERTED
    assert m.total_versions() == 1

    ts2 = ts1 + timedelta(days=1)
    r2 = {"id": 1, "name": "Alice", "val": 20}
    res2 = m.upsert(r2, timestamp=ts2)
    assert res2.action == UpsertAction.UPDATED
    assert m.total_versions() == 2

    # unchanged
    res3 = m.upsert(r2, timestamp=ts2 + timedelta(seconds=1))
    assert res3.action == UpsertAction.UNCHANGED


def test_scd2_late_arriving():
    m = SCD2Manager(natural_key_fields=["id"]) 
    t1 = datetime(2020,1,2, tzinfo=timezone.utc)
    r1 = {"id": 2, "val": 1}
    m.upsert(r1, timestamp=t1)

    late = {"id": 2, "val": 0}
    t_late = datetime(2020,1,1, tzinfo=timezone.utc)
    res = m.upsert(late, timestamp=t_late)
    assert res.action == UpsertAction.LATE_ARRIVING
    assert m.get_history({"id":2})[0].valid_from == t_late

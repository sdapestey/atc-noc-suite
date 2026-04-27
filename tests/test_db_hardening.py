import db as db_module
import pytest
from psycopg2 import OperationalError


class _FakeCursor:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.owner = None

    def execute(self, sql):
        self.calls.append(sql)
        if self.owner is not None and getattr(self.owner, "fail_on_execute", False):
            raise OperationalError("simulated stale connection")

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, closed=0, fail_on_execute=False):
        self.closed = closed
        self.fail_on_execute = fail_on_execute
        self.autocommit = True
        self.cursor_obj = _FakeCursor()
        self.cursor_obj.owner = self
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakePool:
    def __init__(self, conns):
        self._conns = list(conns)
        self.put_calls = []

    def getconn(self):
        return self._conns.pop(0)

    def putconn(self, conn, close=False):
        self.put_calls.append((conn, close))


def test_db_cursor_discards_closed_connection_and_retries(monkeypatch):
    bad = _FakeConn(closed=1)
    good = _FakeConn(closed=0)
    pool = _FakePool([bad, good])
    monkeypatch.setattr(db_module, "init_pool", lambda: pool)

    with db_module.db_cursor() as cur:
        cur.execute("SELECT 1;")

    assert pool.put_calls[0] == (bad, True)
    assert pool.put_calls[-1] == (good, False)
    assert good.commits == 1


def test_db_cursor_retries_once_after_operational_error(monkeypatch):
    first = _FakeConn(fail_on_execute=True)
    second = _FakeConn()
    pool = _FakePool([first, second])
    monkeypatch.setattr(db_module, "init_pool", lambda: pool)

    with db_module.db_cursor() as cur:
        cur.execute("SELECT 1;")

    assert first.rollbacks == 1
    assert second.commits == 1
    assert pool.put_calls[0] == (first, True)
    assert pool.put_calls[-1] == (second, False)


def test_db_cursor_raises_when_retry_is_exhausted(monkeypatch):
    first = _FakeConn(fail_on_execute=True)
    second = _FakeConn(fail_on_execute=True)
    pool = _FakePool([first, second])
    monkeypatch.setattr(db_module, "init_pool", lambda: pool)

    with pytest.raises(OperationalError):
        with db_module.db_cursor() as cur:
            cur.execute("SELECT 1;")

    assert first.rollbacks == 1
    assert second.rollbacks == 1
    assert pool.put_calls == [(first, True), (second, True)]


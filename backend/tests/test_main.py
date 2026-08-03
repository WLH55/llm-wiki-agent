import pytest


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


@pytest.mark.asyncio
async def test_lifespan_does_not_initialize_bootstrap_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.auth.service import bootstrap
    from app.main import app, lifespan
    from app.models import database

    bootstrap_calls = 0

    async def record_bootstrap_call(session: object) -> None:
        nonlocal bootstrap_calls
        bootstrap_calls += 1

    monkeypatch.setattr(bootstrap, "ensure_bootstrap_owner", record_bootstrap_call)
    monkeypatch.setattr(database, "async_session_factory", lambda: _SessionContext())

    async with lifespan(app):
        pass

    assert bootstrap_calls == 0

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import func, select

from vediogen_api import advisor
from vediogen_api.database import SessionLocal, engine, ensure_runtime_schema
from vediogen_api.gateway import ModelGatewayError
from vediogen_api.models import AdvisorRunRow, ModelInvocationRow, ProjectRow, RoutingVersionRow


def create_project(client):
    response = client.post("/api/v1/projects", json={
        "title": "Text-only motorcycle", "initialMessage": "360 orbit, then riding",
        "contentPackId": "motorcycle", "mode": "real-subject",
        "targetPlatform": "douyin", "locale": "zh-CN", "assetVersionIds": [],
    })
    assert response.status_code == 201
    return response.json()["id"]


def count(model):
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(model))


def delayed_gateway(monkeypatch, failure=None):
    entered, release, joined = Event(), Event(), Event()
    original = advisor.generate_creative_advice
    calls = []

    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout=10)

    def generate(session, project):
        calls.append(project.id)
        entered.set()
        assert release.wait(10), "Test did not release the provider"
        if failure:
            raise failure
        return original(session, project)

    monkeypatch.setattr(advisor, "Future", ObservedFuture)
    monkeypatch.setattr(advisor, "generate_creative_advice", generate)
    return entered, release, joined, calls


def test_concurrent_refresh_shares_one_invocation_and_cached_result(client, monkeypatch):
    project_id = create_project(client)
    url = f"/api/v1/projects/{project_id}/advisor-runs"
    entered, release, joined, calls = delayed_gateway(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, url)
        try:
            assert entered.wait(5)
            second = pool.submit(client.post, url)
            assert joined.wait(5)
        finally:
            release.set()
        one, two = first.result(10), second.result(10)
    assert one.status_code == two.status_code == 202
    assert one.json() == two.json()
    assert calls == [project_id]
    assert count(AdvisorRunRow) == count(ModelInvocationRow) == 1
    assert not advisor._inflight
    # A new HTTP request/session also reuses the persisted success.
    assert client.post(url).json() == one.json()
    assert count(ModelInvocationRow) == 1


@pytest.mark.parametrize("change", ["message", "title", "asset", "route", "legacy"])
def test_changed_input_does_not_reuse_old_advice(client, change):
    project_id = create_project(client)
    url = f"/api/v1/projects/{project_id}/advisor-runs"
    first = client.post(url).json()
    if change == "message":
        assert client.post(f"/api/v1/projects/{project_id}/messages", json={
            "text": "Keep the leather rider as final shot", "assetVersionIds": [],
        }).status_code == 201
    else:
        with SessionLocal() as session:
            project = session.get(ProjectRow, project_id)
            if change == "title":
                project.title = "New direction"
            elif change == "asset":
                project.asset_versions = [{"id": "reference", "kind": "image", "sha256": "new"}]
            elif change == "route":
                previous = session.scalar(select(RoutingVersionRow))
                session.add(RoutingVersionRow(id="new-route", version=99,
                    bindings=previous.bindings, status="published", change_note="Test route"))
            else:
                session.get(AdvisorRunRow, first["id"]).input_fingerprint = None
            session.commit()
    second = client.post(url)
    assert second.status_code == 202
    assert second.json()["id"] != first["id"]
    assert count(ModelInvocationRow) == 2


def test_input_changes_during_generation_do_not_publish_stale_result(client, monkeypatch):
    project_id = create_project(client)
    url = f"/api/v1/projects/{project_id}/advisor-runs"
    entered, release, _, calls = delayed_gateway(monkeypatch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, url)
        try:
            assert entered.wait(5)
            assert client.post(f"/api/v1/projects/{project_id}/messages", json={
                "text": "New ending", "assetVersionIds": [],
            }).status_code == 201
            assert client.post(url).status_code == 409
        finally:
            release.set()
        assert pending.result(10).status_code == 409
    workspace = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert workspace["latestAdvisorRunId"] is None
    assert workspace["messages"][-1]["text"] == "New ending"
    assert count(AdvisorRunRow) == count(ModelInvocationRow) == 1
    assert client.post(url).status_code == 202
    assert calls == [project_id, project_id]


def test_concurrent_failures_share_error_and_allow_explicit_retry(client, monkeypatch):
    project_id = create_project(client)
    url = f"/api/v1/projects/{project_id}/advisor-runs"
    original = advisor.generate_creative_advice
    entered, release, joined, calls = delayed_gateway(monkeypatch, ModelGatewayError("Provider timeout"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, url)
        try:
            assert entered.wait(5)
            second = pool.submit(client.post, url)
            assert joined.wait(5)
        finally:
            release.set()
        one, two = first.result(10), second.result(10)
    assert one.status_code == two.status_code == 502
    assert one.json() == two.json() == {"detail": "Provider timeout"}
    assert calls == [project_id]
    assert not advisor._inflight
    assert count(AdvisorRunRow) == 0
    monkeypatch.setattr(advisor, "generate_creative_advice", original)
    assert client.post(url).status_code == 202


def test_other_projects_are_not_blocked_by_slow_provider(client, monkeypatch):
    slow_id, other_id = create_project(client), create_project(client)
    original = advisor.generate_creative_advice
    entered, release = Event(), Event()

    def generate(session, project):
        if project.id == slow_id:
            entered.set()
            assert release.wait(10)
        return original(session, project)

    monkeypatch.setattr(advisor, "generate_creative_advice", generate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f"/api/v1/projects/{slow_id}/advisor-runs")
        try:
            assert entered.wait(5)
            assert client.post(f"/api/v1/projects/{other_id}/advisor-runs").status_code == 202
        finally:
            release.set()
        assert pending.result(10).status_code == 202


def test_existing_database_additive_migration_preserves_results(client):
    project_id = create_project(client)
    first = client.post(f"/api/v1/projects/{project_id}/advisor-runs").json()
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE advisor_runs DROP COLUMN input_fingerprint")
    ensure_runtime_schema()
    ensure_runtime_schema()
    assert client.get(f"/api/v1/advisor-runs/{first['id']}").json() == first
    with SessionLocal() as session:
        assert session.get(AdvisorRunRow, first["id"]).input_fingerprint is None

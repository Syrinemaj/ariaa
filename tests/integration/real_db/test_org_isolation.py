"""
Multi-tenant isolation: a user of organisation A must never read or use
organisation B's data, even when they know B's identifiers.

Each case has a positive control (B's own admin gets the resource), so a
404 for A proves isolation rather than a broken route.
"""
from uuid import uuid4

import pytest

from app.auth.password import hash_password
from app.core.config import settings
from app.models.analysis_run import AnalysisRun
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.connection import Connection
from app.models.embedding import EndpointEmbedding
from app.models.endpoint import Endpoint
from app.models.organization import Organization
from app.models.user import User, UserRole

from tests.integration.real_db.conftest import login_and_get_token

PASSWORD = "Isolation@123"
# Same vector for every stored endpoint and for the query: cosine distance 0,
# so B's endpoint would be the top match if the org filter were missing.
VECTOR = [1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 1)


class _FakeEmbeddingClient:
    async def create_embedding_query_async(self, text):
        return VECTOR


def _make_org_with_admin(db, label):
    org = Organization(id=str(uuid4()), name=f"isolation-{label}-{uuid4()}")
    db.add(org)
    db.commit()
    email = f"isolation-{label}-{uuid4().hex[:8]}@example.com"
    admin = User(
        id=str(uuid4()),
        org_id=org.id,
        email=email,
        full_name=f"Admin {label}",
        hashed_password=hash_password(PASSWORD),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    return org, admin


def _make_run_with_endpoint(db, org, admin, path):
    run = AnalysisRun(
        id=str(uuid4()), org_id=org.id, created_by_user_id=admin.id,
        file_name=f"{org.name}.har", status="completed",
    )
    db.add(run)
    db.commit()
    endpoint = Endpoint(
        id=str(uuid4()), org_id=org.id, run_id=run.id, method="GET", path=path,
        canonical_key=f"{org.id}:GET {path}", business_domain="hr",
    )
    db.add(endpoint)
    db.commit()
    db.add(EndpointEmbedding(
        id=str(uuid4()), endpoint_id=endpoint.id,
        embedding_text=f"GET {path} list employees", embedding=VECTOR,
    ))
    db.commit()
    return run, endpoint


@pytest.fixture()
def two_orgs(db):
    org_a, admin_a = _make_org_with_admin(db, "a")
    org_b, admin_b = _make_org_with_admin(db, "b")
    run_a, endpoint_a = _make_run_with_endpoint(db, org_a, admin_a, "/api/a/employees")
    run_b, endpoint_b = _make_run_with_endpoint(db, org_b, admin_b, "/api/b/employees")
    connection_b = Connection(
        id=str(uuid4()), org_id=org_b.id, name=f"conn-b-{uuid4()}",
        base_url="https://api.example.com", environment="test", auth_type="api_key",
        encrypted_secret="not-a-real-secret", status="active", created_by=admin_b.id,
    )
    db.add(connection_b)
    db.commit()

    yield {
        "admin_a": admin_a, "admin_b": admin_b,
        "run_b": run_b, "endpoint_a": endpoint_a, "endpoint_b": endpoint_b,
        "connection_b": connection_b,
    }

    db.query(Connection).filter(Connection.id == connection_b.id).delete()
    for endpoint in (endpoint_a, endpoint_b):
        db.query(EndpointEmbedding).filter(EndpointEmbedding.endpoint_id == endpoint.id).delete()
        db.query(Endpoint).filter(Endpoint.id == endpoint.id).delete()
    db.query(AnalysisRun).filter(AnalysisRun.id.in_([run_a.id, run_b.id])).delete()
    user_ids = [admin_a.id, admin_b.id]
    # Logins during the tests wrote audit rows and refresh tokens for these users.
    db.query(AuditLog).filter(AuditLog.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
    db.query(RefreshToken).filter(RefreshToken.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(user_ids)).delete()
    db.query(Organization).filter(Organization.id.in_([org_a.id, org_b.id])).delete()
    db.commit()


def _auth(client, user):
    return {"Authorization": f"Bearer {login_and_get_token(client, user.email, PASSWORD)}"}


def test_user_cannot_read_other_org_endpoints(client, two_orgs):
    run_b = two_orgs["run_b"].id
    headers_a = _auth(client, two_orgs["admin_a"])
    headers_b = _auth(client, two_orgs["admin_b"])

    # Positive control: B reads its own run.
    assert client.get(f"/registry/runs/{run_b}/endpoints", headers=headers_b).status_code == 200

    assert client.get(f"/registry/runs/{run_b}", headers=headers_a).status_code == 404
    assert client.get(f"/registry/runs/{run_b}/endpoints", headers=headers_a).status_code == 404


def test_user_cannot_read_or_use_other_org_connection(client, two_orgs):
    conn_b = two_orgs["connection_b"].id
    headers_a = _auth(client, two_orgs["admin_a"])
    headers_b = _auth(client, two_orgs["admin_b"])

    # Positive control: B reads its own connection.
    assert client.get(f"/connections/{conn_b}", headers=headers_b).status_code == 200

    assert client.get(f"/connections/{conn_b}", headers=headers_a).status_code == 404
    assert client.post(f"/connections/{conn_b}/test", headers=headers_a).status_code == 404
    listed = client.get("/connections", headers=headers_a).json()
    assert conn_b not in str(listed)


def test_semantic_search_never_returns_other_org_endpoints(client, two_orgs):
    headers_a = _auth(client, two_orgs["admin_a"])
    headers_b = _auth(client, two_orgs["admin_b"])

    state = client.app.state
    saved = (getattr(state, "embedding_client", None), getattr(state, "ai_client", None))
    state.embedding_client, state.ai_client = _FakeEmbeddingClient(), None
    try:
        body = {"query": "list employees", "top_k": 50}
        ids_a = {r["endpoint_id"] for r in client.post("/rag/search", json=body, headers=headers_a).json()["results"]}
        ids_b = {r["endpoint_id"] for r in client.post("/rag/search", json=body, headers=headers_b).json()["results"]}
    finally:
        state.embedding_client, state.ai_client = saved

    # Positive controls: each org finds its own endpoint (same vector, score 1).
    assert two_orgs["endpoint_a"].id in ids_a
    assert two_orgs["endpoint_b"].id in ids_b
    # Isolation: neither sees the other's endpoint.
    assert two_orgs["endpoint_b"].id not in ids_a
    assert two_orgs["endpoint_a"].id not in ids_b

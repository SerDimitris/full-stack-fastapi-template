import os
import tempfile

from fastapi.testclient import TestClient

from app.core.config import settings


def test_tenant_crud_and_routing_isolation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    # 1. Create a temporary SQLite database for Tenant A
    temp_db_a = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db_a_path = temp_db_a.name
    temp_db_a.close()

    tenant_a_db_uri = f"sqlite:///{temp_db_a_path.replace(os.sep, '/')}"

    tenant_data = {
        "id": "tenant_a",
        "name": "Tenant Alpha",
        "db_uri": tenant_a_db_uri,
        "is_active": True
    }

    # 2. Create the tenant via API
    r = client.post(
        f"{settings.API_V1_STR}/tenants/",
        headers=superuser_token_headers,
        json=tenant_data,
    )
    assert r.status_code == 201, f"Failed to create tenant: {r.status_code} - {r.text}"
    created_tenant = r.json()

    assert created_tenant["id"] == "tenant_a"
    assert created_tenant["db_uri"] == tenant_a_db_uri

    # 3. Read the tenant back
    r = client.get(
        f"{settings.API_V1_STR}/tenants/tenant_a",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Tenant Alpha"

    # 4. Check list of tenants
    r = client.get(
        f"{settings.API_V1_STR}/tenants/",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200
    tenants = r.json()
    assert any(t["id"] == "tenant_a" for t in tenants)

    # 5. Authenticate against Tenant A to get a tenant-specific token.
    # Note: When Tenant A was initialized dynamically in get_tenant_engine,
    # it ran init_db(session) which created the first superuser inside Tenant A's database.
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    r = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        headers={"X-Tenant-ID": "tenant_a"},
        data=login_data,
    )
    assert r.status_code == 200, f"Failed to login to Tenant A: {r.text}"
    tokens = r.json()
    tenant_a_token = tokens["access_token"]

    headers_with_tenant = {"Authorization": f"Bearer {tenant_a_token}"}

    # Request the current user profile on Tenant A.
    r = client.get(
        f"{settings.API_V1_STR}/users/me",
        headers=headers_with_tenant,
    )
    assert r.status_code == 200
    user_data = r.json()
    assert user_data["email"] == settings.FIRST_SUPERUSER


    # 6. Clean up temporary database file
    try:
        os.unlink(temp_db_a_path)
    except OSError:
        pass

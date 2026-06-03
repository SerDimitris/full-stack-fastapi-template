from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.deps import LandlordSessionDep, get_current_active_superuser
from app.models import Message, Tenant, TenantCreate, TenantPublic, TenantUpdate

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/", response_model=TenantPublic, status_code=201, dependencies=[Depends(get_current_active_superuser)])
def create_tenant(*, session: LandlordSessionDep, tenant_in: TenantCreate) -> Any:
    """
    Create a new tenant. Only accessible by superusers.
    """
    tenant = session.get(Tenant, tenant_in.id)
    if tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with ID '{tenant_in.id}' already exists.",
        )
    db_tenant = Tenant.model_validate(tenant_in)
    session.add(db_tenant)
    session.commit()
    session.refresh(db_tenant)
    return db_tenant


@router.get("/", response_model=list[TenantPublic], dependencies=[Depends(get_current_active_superuser)])
def read_tenants(*, session: LandlordSessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve tenants. Only accessible by superusers.
    """
    tenants = session.exec(select(Tenant).offset(skip).limit(limit)).all()
    return tenants


@router.get("/{tenant_id}", response_model=TenantPublic, dependencies=[Depends(get_current_active_superuser)])
def read_tenant_by_id(*, session: LandlordSessionDep, tenant_id: str) -> Any:
    """
    Get a specific tenant's metadata. Only accessible by superusers.
    """
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found.",
        )
    return tenant


@router.put("/{tenant_id}", response_model=TenantPublic, dependencies=[Depends(get_current_active_superuser)])
def update_tenant(
    *, session: LandlordSessionDep, tenant_id: str, tenant_in: TenantUpdate
) -> Any:
    """
    Update a tenant's details. Only accessible by superusers.
    """
    db_tenant = session.get(Tenant, tenant_id)
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found.",
        )
    tenant_data = tenant_in.model_dump(exclude_unset=True)
    db_tenant.sqlmodel_update(tenant_data)
    session.add(db_tenant)
    session.commit()
    session.refresh(db_tenant)
    return db_tenant


@router.delete("/{tenant_id}", response_model=Message, dependencies=[Depends(get_current_active_superuser)])
def delete_tenant(*, session: LandlordSessionDep, tenant_id: str) -> Any:
    """
    Delete a tenant. Only accessible by superusers.
    """
    db_tenant = session.get(Tenant, tenant_id)
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found.",
        )
    session.delete(db_tenant)
    session.commit()
    return Message(message=f"Tenant '{tenant_id}' deleted successfully.")

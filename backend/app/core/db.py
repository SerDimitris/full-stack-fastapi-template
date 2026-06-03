from threading import Lock

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
landlord_engine = engine

tenant_engines: dict[str, Engine] = {}
tenant_engines_lock = Lock()


def get_tenant_engine(tenant_id: str, db_uri: str) -> Engine:
    with tenant_engines_lock:
        if tenant_id not in tenant_engines:
            # Create a new engine for the tenant
            tenant_engine = create_engine(db_uri)
            tenant_engines[tenant_id] = tenant_engine
            # Initialize tenant DB tables if they don't exist
            SQLModel.metadata.create_all(tenant_engine)
            # Create default superuser inside this tenant's database
            with Session(tenant_engine) as session:
                init_db(session)
        return tenant_engines[tenant_id]


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines

    # This works because the models are already imported and registered from app.models
    SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)


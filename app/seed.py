from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.models import Tenant


DEMO_TENANTS = [
    {
        "id": UUID("11111111-1111-4111-8111-111111111111"),
        "name": "Northwind Retail",
    },
    {
        "id": UUID("22222222-2222-4222-8222-222222222222"),
        "name": "Contoso Shop",
    },
]


def main() -> None:
    with SessionLocal.begin() as session:
        statement = (
            insert(Tenant)
            .values(DEMO_TENANTS)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.execute(statement)

    print("Demo tenants ready.")


if __name__ == "__main__":
    main()
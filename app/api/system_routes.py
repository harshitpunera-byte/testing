from fastapi import APIRouter

from app.services.system_service import clear_application_data, get_system_health


router = APIRouter(prefix="/system", tags=["System"])


@router.post("/clear-database")
def clear_database():
    return clear_application_data()


@router.get("/health")
def system_health():
    return get_system_health()

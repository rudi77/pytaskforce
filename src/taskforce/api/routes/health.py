from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    version: str

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness probe - is the service running?"""
    return HealthResponse(status="healthy", version="1.0.0")

@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness probe - can the service handle requests?"""
    # Check dependencies (DB, external APIs)
    try:
        # Test DB connectivity
        # await check_database_connection()
        return HealthResponse(status="ready", version="1.0.0")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready: {str(e)}"
        )


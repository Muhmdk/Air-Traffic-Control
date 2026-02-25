import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "sector",
        "sector_id": os.getenv("SECTOR_ID", "SECTOR_A"),
    }

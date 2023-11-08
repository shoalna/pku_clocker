from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from . import schemas, db_utils


router = APIRouter()



@router.post("/customers")
async def create_customer(
    customer: schemas.Customer, db: AsyncSession = Depends(get_session)
):
    return await db_utils.create_customer(db, customer)
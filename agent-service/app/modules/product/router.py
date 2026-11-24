from decimal import Decimal

from app.infra.database import get_session
from app.modules.product.models import Product
from app.modules.product.schemas import ProductResponse
from app.modules.product.service import ProductService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

# 挂载路由
router = APIRouter(prefix="/api/v1/products", tags=["products"])

# 获取前端product service对象，方便后续调用
async def get_product_service(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProductService:
    return ProductService(session)


@router.get("", response_model=list[ProductResponse])
async def list_products(
    category: str | None = None,
    # router -> get_product_service -> get_session -> yield session暂停执行，交出session
    service: ProductService = Depends(get_product_service),  # noqa: B008
) -> list[Product]:
    return await service.list_products(category)


@router.get("/candidates", response_model=list[ProductResponse])
async def list_candidates(
    categories: list[str] = Query(min_length=1),  # noqa: B008
    premium_min: Decimal | None = None,
    limit_per_category: int = 5,
    service: ProductService = Depends(get_product_service),  # noqa: B008
) -> list[Product]:
    return await service.list_candidates(
        categories=categories,
        premium_min=premium_min,
        limit_per_category=limit_per_category,
    )

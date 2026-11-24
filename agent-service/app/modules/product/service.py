# Service 负责组织业务流程：
# 开启事务（如果有必要的话）、调用 Repository，并把数据库 Model 转换为接口 Schema

from decimal import Decimal

from app.modules.product.models import Product
from app.modules.product.repository import ProductRepository
from sqlalchemy.ext.asyncio import AsyncSession


class ProductService: # 创建一个类方便调用
    def __init__(self, session: AsyncSession):
        self.session = session # 管理事务
        self.repository = ProductRepository(session)# 创建Repository对象，repository变成成员变量

    async def list_products(
        self,
        category: str | None = None,
    ) -> list[Product]:
        return await self.repository.find_by_category(category)


    async def list_candidates(
        self,
        categories: list[str],
        premium_min: Decimal | None,
        limit_per_category: int,
    ) -> list[Product]:
        candidate_products: list[Product] = []

        for category in dict.fromkeys(categories):
            products = await self.repository.find_limited_by_category(
                category=category,
                premium_min=premium_min,
                limit=limit_per_category,
            )
            candidate_products.extend(products)

        return candidate_products
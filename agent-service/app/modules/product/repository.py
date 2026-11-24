# repository -> 仓库，该文件用于处理数据库访问  
from decimal import Decimal

from app.modules.product.models import Product
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_category(
        self,
        category: str | None = None,
    ) -> list[Product]:
        # 1.组装查询条件 + 动态查询
        # 1.1.默认只查询active状态的产品
        conditions = [Product.status == "active"] # 设置为列表
        # 1.2.如果有category，则添加category过滤
        if category:
            conditions.append(Product.category == category)

        # 2.查询产品列表
        products = await self.session.scalars( # 省去execute，将return的scalars提前
            select(Product)
            .where(*conditions)# *号解包列表，拆成条件
            .order_by(Product.id.asc())
        )
        # return list(products.all())# .all类型标注为sequence[Product]和我们规定的List[Product]类型冲突
        return products.all() # pyright: ignore[reportReturnType]


    async def find_limited_by_category(
        self,
        category: str,
        premium_min: Decimal | None,
        limit: int,
    ) -> list[Product]:
        conditions = [
            Product.status == "active",
            Product.category == category,
        ]
        # 动态查询: 如果premium_min不为None，则添加条件
        if premium_min is not None:
            # 前者为数据库的字段，后者为前端传入的参数
            conditions.append(Product.min_premium < premium_min)

        products = await self.session.scalars(
            select(Product)
            .where(*conditions) # 解包
            .order_by(
                Product.min_premium.asc().nullslast(),# nulls last()表示将null值放在最后
                Product.id.asc(),# 先按价格进行排序,价格一样再以id排序
            )
            .limit(limit)
        )
        return products.all() # pyright: ignore[reportReturnType]
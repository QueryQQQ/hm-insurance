# 该文件用于定义请求和约束模型 定义的是前端访问的类类型

from decimal import Decimal

from app.common.schemas import BaseSchemas


class ProductResponse(BaseSchemas):
    """保险产品响应结果"""
    
    id: int
    name: str
    clause_name: str
    category: str
    insurer: str
    image_url: str
    description: str
    min_premium: Decimal | None
    max_premium: Decimal | None
    target_group: str | None
    highlights: list[str]
    status: str
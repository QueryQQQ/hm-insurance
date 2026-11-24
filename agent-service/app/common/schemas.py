

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class BaseSchemas(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# 定义一个泛型
T = TypeVar("T")

class PageResult(BaseSchemas, Generic[T]):
    """通用分类结果"""
    items: list[T]
    page: int
    page_size: int
    total: int
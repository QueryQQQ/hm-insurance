from datetime import datetime
from uuid import UUID

from app.common.schemas import BaseSchemas
from pydantic import Field, field_validator


class ChatThreadCreate(BaseSchemas):
    """创建会话请求
    并接收前端的json"""

    title: str = Field(default="新会话", min_length=1, max_length=200) # 接收json


    # 作前置校验避免出现只有空格的title
    @field_validator("title", mode="before")# ("校验对象","pydantic类型转换之前或之后检验")
    @classmethod # 类方法 相当于格式
    def normalize_title(cls, value: str) -> str:# (类本身, 参数)
        return value.strip()# strip去掉首尾空格,转义符,确保没有只有空格的格式传入


class ChatThreadResponse(BaseSchemas):
    """会话响应"""  

    id: UUID
    title: str
    # user_id作为敏感信息不往前端传
    created_at: datetime
    updated_at: datetime
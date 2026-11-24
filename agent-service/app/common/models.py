# common 是公共模块 models是公共表映射模型
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from sqlalchemy import DateTime, func


# 定义SQLAlchemy的基类，所有数据库表模型都必须继承
# 同时给模型定义统一的控制台输出格式
class Base(DeclarativeBase):
    def __repr__(self) -> str: # repr就是根据不同的数据类型进行加工，例如输出字符串加单引号
        """通用的repr函数，用于控制台输出对象信息"""
        cls_name = self.__class__.__name__
        attrs = {}
        for key, val in vars(self).items():
            if key.startswith("_"):
                continue
            if isinstance(val, datetime):
                attrs[key] = val.strftime("%Y-%m-%d %H:%M:%S")
            else:
                attrs[key] = val
        return f"{cls_name}({attrs})"# 返回 类名+属性字典


# 通用的时间戳【混入类】，这样其它数据模型不用重复定义时间相关字段
# 不定义在基类是因为有一些不需要而大多数类需要
class CreateAtMixin:
    # func.now() 会让数据库在插入时自动生成服务器时间（如 PostgreSQL 的 NOW()）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

class UpdateAtMixin:
    # onupdate=func.now() 会在每次数据行被 UPDATE 时，由 SQLAlchemy 自动更新该字段
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
# 增删改查放到一个类里面调用
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatThread


class ChatThreadRepository:

    # 拿到session,后续所有函数可以直接调用session
    def __init__(self, session: AsyncSession) -> None:# self实例引用,用就是调用了这个实例
        self.session = session# 将外部的session传入到self这个实例的session属性上


    # 将chat_thread在service封装,直接接收chat_thread,保留最纯粹的数据库操作
    # 创建会话
    async def add(self, chat_thread: ChatThread):
        # chat_threads = ChatThread(user_id = user_id, title = title)# 将ORM对象执行结果定义一个变量存储
        self.session.add(chat_thread)

    # 查询会话列表
    async def list_by_user_id(self, user_id: int):
        # 1.根据user_id查询
        threads = await self.session.scalars(
            # 查表传类,添数据传对象,字段对应类的属性
            # 表结构相同,直接用同一个类,不用再定义
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc(),ChatThread.created_at.desc()) #先按更新时间,再按创建时间
        )
        # 2.返回对象
        return threads

    # 校验用户是否为指定用户
    async def check_required_owner(self, user_id: int, id: str):
    # select * from chat_threard
    # WHERE user_id = 1 AND id = c22be77f-d6ab-411e-897d-974a63cf4940
        chat_thread = await self.session.scalar(
            select(ChatThread)
            .where(ChatThread.id == id , ChatThread.user_id == user_id)
        )
        # 2.返回对象
        return chat_thread

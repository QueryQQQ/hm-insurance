# sevice专门用于管理事务
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import ChatThreadNotFoundError
from .models import ChatThread
from .repository import ChatThreadRepository


class ChatThreadService:
    def __init__(self, session: AsyncSession):  
        self.session = session
        self.repository = ChatThreadRepository(session)

    # 实现创建业务
    async def add(self, user_id: int, title: str) -> ChatThread:
        # 上下文管理,开启事务session,运行完成,自动commit,出现异常,自动rollback
        async with self.session.begin():
            # 创建对象,对象映射到数据库
            chat_thread = ChatThread(user_id = user_id, title = title)
            # 新增对象就是在事务插入一条数据
            await self.repository.add(chat_thread)
            return chat_thread

    # 实现查询会话列表
    async def list_by_user_id(self, user_id: int):
        return await self.repository.list_by_user_id(user_id)

    # 重命名用户会话
    async def rename(self, user_id: int, id: str, title: str):
        async with self.session.begin():
        # 1.校验用户是否为指定用户
            chat_thread = await self.repository.check_required_owner(user_id, id)
        if not chat_thread:
            raise ChatThreadNotFoundError()
        # 2.修改会话标题
        chat_thread.title = title
        # 3.保存修改
        await self.session.flush() # flush将修改同步到数据库,但不提交事务
        await self.session.refresh(chat_thread) # refresh将数据库最新数据同步到对象,保证返回的对象是最新的
        # 4.返回修改后的对象
        return chat_thread

    
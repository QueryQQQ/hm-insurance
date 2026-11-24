from typing import Annotated

from app.infra.database import get_session
from app.modules.chat_threads.schemas import ChatThreadCreate, ChatThreadResponse
from app.modules.chat_threads.service import ChatThreadService
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/chat-threads", tags=["会话管理的接口"])


# 创建,查询,删除会话都要用到service
# 不断重复写service = ChatThreadService(session),改成依赖注入
# 后续需要什么就依赖注入什么
async def get_service(
        session: AsyncSession = Depends(get_session)  # noqa: B008
):
    return ChatThreadService(session)

# 创建会话
@router.post("", response_model = ChatThreadResponse)
# 业务逻辑: 1.获取service 2.创建会话 3.返回结果
async def create_chat_thread(
    request: ChatThreadCreate,# 前端传json被pydantic接收,并校验,返回一个对象
    user_id: Annotated[int , Header(alias="x-user-id")],# annotated注释的
    # 等价于user_id: int = Header 说明来源与请求头
    service: ChatThreadService = Depends(get_service)  # noqa: B008
):
    result = await service.add(user_id, request.title) 
    return result


# 查询会话列表
@router.get("", response_model = list[ChatThreadResponse])
async def list_by_user(
    user_id: Annotated[int , Header(alias="x-user-id")],
    service: ChatThreadService = Depends(get_service)  # noqa: B008
):
    result = await service.list_by_user_id(user_id)
    return result


# 重命名会话
@router.patch("/{thread_id}", response_model = ChatThreadResponse)
async def rename_chat_thread(
    thread_id: str,
    request: ChatThreadCreate,
    user_id: Annotated[int , Header(alias="x-user-id")],
    service: ChatThreadService = Depends(get_service)  # noqa: B008
):
    result = await service.rename(user_id, thread_id, request.title)
    return result
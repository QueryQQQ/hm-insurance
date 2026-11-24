
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.core.logging import configure_logging, get_logger

# 日志配置
configure_logging(settings.logging.level)# 不写固定值，方便后续改动，只改env里面即可
# 后去日志记录器
logger = get_logger(__name__) # __name__当前模块名


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"【{settings.app.name}】应用启动中...")
    from app.infra.database import check_database, close_database
    try:
        await check_database()
        yield # 返回一个值并暂停函数，下次直接从暂停位置开始
    finally:
        logger.info("应用关闭中... ")
        await close_database()


# 初始化FasrAPI
app = FastAPI(
    title=settings.app.name,
    debug=settings.app.debug,
    lifespan=lifespan, # 由于连接池默认是懒加载，第一次访问时才会初始化。
    #  所以，我们需要在项目启动时调用check_database，测试并初始化连接，在项目停止时调用close_db，关闭数据库连接池。
)


# 挂载路由
from app.modules.chat_threads.router import router as chat_thread_router
from app.modules.product.router import router as product_router

app.include_router(product_router)
app.include_router(chat_thread_router)


# 测试接口，健康检查
@app.get("/healthy", summary="健康检测接口")
async def healthy() -> dict[str, str]:
    logger.info("健康检测接口正常调用") # 日志记录
    return{"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",# 分别为`agent-service/app` 这个 Python 包，main.py,FastAPI对象
        host=settings.app.host,
        port=settings.app.port,
        reload=False
    )


# 统一处理异常信息，由于每新增一种异常，都要继续给main.py 添加新的异常处理函数来捕获异常
# 直接自定义异常，使异常信息中自带stauts、code、message信息
# 统一异常处理，基于异常中自带的status、code、message返回结果
@app.exception_handler(ApplicationError)
def handle_exception(request: Request, exc: ApplicationError):
    logger.error(f"处理异常, 请求路径: {request.url}, 异常信息: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,  # 错误码
            "message": exc.message, # 错误code
        }
    )
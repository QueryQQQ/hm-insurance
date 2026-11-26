from pathlib import Path

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 以当前文件为基准，找向上2级的父目录，也就是项目的根目录
APP_ROOT = Path(__file__).resolve().parents[2]

# 确定了项目根目录才好定位env文件
class EnvSettings(BaseSettings):
    """公共settings，配置.env文件位置"""
    model_config = SettingsConfigDict(
        env_file=(APP_ROOT / ".env",), # 寻找env
        env_file_encoding="utf-8",
        extra="ignore",  # settings中未定义的字段被忽略
    )

# 四个类对应env的四个设置
class AppSettings(EnvSettings):
    """应用相关设置"""
    # 加alias方便定位env里面名字
    name: str = Field(alias="APP_NAME")
    host: str = Field(alias="APP_HOST", default="127.0.0.1")
    port: int = Field(alias="APP_PORT", default=8001)
    debug: bool = Field(alias="APP_DEBUG", default=True, description="是否开启FastAPI的DEBUG模式")

class DatabaseSettings(EnvSettings):
    """数据库相关设置"""
    host: str = Field(alias="DB_HOST", default="localhost")
    port: int = Field(alias="DB_PORT", default=5432)
    name: str = Field(alias="DB_NAME", default="insurance")
    user: str = Field(alias="DB_USER", default="insurance")
    password: str = Field(alias="DB_PASSWORD", default="insurance123")
    echo: bool = Field(alias="DB_ECHO", default=False)
    pool_size: int = Field(alias="DB_POOL_SIZE", default=5)
    max_overflow: int = Field(alias="DB_MAX_OVERFLOW", default=10)
    pool_recycle: int = Field(alias="DB_POOL_RECYCLE", default=1800)

    @computed_field
    @property
    def url(self) -> str:
        # 自动拼接URL路径
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            host=self.host,
            port=self.port,
            username=self.user,
            password=self.password
        ).encoded_string()

class LLMSettings(EnvSettings):
    """模型相关配置"""
    api_key: str = Field(alias="DEEPSEEK_API_KEY")
    chat_model: str = Field(alias="CHAT_MODEL", default="deepseek-v4-flash")

class LoggingSettings(EnvSettings):
    """日志相关配置"""
    level: str = Field(alias="LOGGING_LEVEL", default="INFO") # 可选值：DEBUG、INFO、WARNING、ERROR、CRITICAL


# 这里处理pylance静态编辑报错函数签名冲突
# pylance认为没有默认值是必填参数，代码上没有传入，而实际上由于继承了BaseSetting，运行时Pydantic会读.env获取值，从而静态检查报错
def create_app_settings() -> AppSettings:
    return AppSettings()  # pyright: ignore[reportCallIssue]

def create_llm_settings() -> LLMSettings:
    return LLMSettings()  # pyright: ignore[reportCallIssue]
 

class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=create_app_settings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=create_llm_settings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

# 项目启动直接初始化
settings = Settings()



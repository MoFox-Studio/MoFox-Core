import os
import socket

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from rich.traceback import install
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from uvicorn import Config
from uvicorn import Server as UvicornServer

from src.common.logger import get_logger
from src.config.config import global_config as bot_config

install(extra_lines=3)

logger = get_logger("Server")


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """自定义速率限制超出处理器以解决类型提示问题"""
    # 由于此处理器专门用于 RateLimitExceeded，我们可以安全地断言异常类型。
    # 这满足了类型检查器的要求，并确保了运行时安全。
    assert isinstance(exc, RateLimitExceeded)
    return _rate_limit_exceeded_handler(request, exc)


class Server:
    def __init__(self, host: str | None = None, port: int | None = None, app_name: str = "MoFox-Bot"):
        assert bot_config is not None
        # 根据配置初始化速率限制器
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[bot_config.plugin_http_system.plugin_api_rate_limit_default],
        )

        self.app = FastAPI(title=app_name)
        self.host: str = "127.0.0.1"
        self.port: int = 8080
        self._server: UvicornServer | None = None
        self.set_address(host, port)

        # 设置速率限制
        self.app.state.limiter = limiter
        self.app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        # 根据配置决定是否添加中间件
        if bot_config.plugin_http_system.plugin_api_rate_limit_enable:
            logger.info(f"已为插件API启用全局速率限制: {bot_config.plugin_http_system.plugin_api_rate_limit_default}")
            self.app.add_middleware(SlowAPIMiddleware)

        # 配置 CORS
        origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:11451",
            "http://127.0.0.1:11451",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:12138",
            "http://localhost:12318"
            # 在生产环境中，您应该添加实际的前端域名
        ]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,  # 是否支持 cookie
            allow_methods=["*"],  # 允许所有 HTTP 方法
            allow_headers=["*"],  # 允许所有 HTTP 请求头
        )

    def register_router(self, router: APIRouter, prefix: str = ""):
        """注册路由

        APIRouter 用于对相关的路由端点进行分组和模块化管理：
        1. 可以将相关的端点组织在一起，便于管理
        2. 支持添加统一的路由前缀
        3. 可以为一组路由添加共同的依赖项、标签等

        示例:
            router = APIRouter()

            @router.get("/users")
            def get_users():
                return {"users": [...]}

            @router.post("/users")
            def create_user():
                return {"msg": "user created"}

            # 注册路由，添加前缀 "/api/v1"
            server.register_router(router, prefix="/api/v1")
        """
        self.app.include_router(router, prefix=prefix)

    def set_address(self, host: str | None = None, port: int | None = None):
        """设置服务器地址和端口"""
        if host:
            self.host = host
        if port:
            self.port = port

    def _is_port_in_use(self, port: int):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    async def run(self):
        """启动服务器"""
        if self._is_port_in_use(self.port):
            error_msg = f"端口 {self.port} 已被占用，无法启动服务器。请检查是否有其他程序正在使用该端口，或修改配置文件中的端口设置。"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"将在 {self.host}:{self.port} 上启动服务器")
        # 禁用 uvicorn 默认日志和访问日志
        config = Config(app=self.app, host=self.host, port=self.port, log_config=None, access_log=False)
        self._server = UvicornServer(config=config)
        try:
            await self._server.serve()
        except KeyboardInterrupt:
            await self.shutdown()
            raise
        except Exception as e:
            await self.shutdown()
            raise RuntimeError(f"服务器运行错误: {e!s}") from e
        finally:
            await self.shutdown()

    async def shutdown(self):
        """安全关闭服务器"""
        if self._server:
            self._server.should_exit = True
            await self._server.shutdown()
            self._server = None

    def get_app(self) -> FastAPI:
        """获取 FastAPI 实例"""
        return self.app


global_server = None


def get_global_server() -> Server:
    """获取全局服务器实例"""
    global global_server
    if global_server is None:
        host = os.getenv("HOST", "127.0.0.1")
        port_str = os.getenv("PORT", "8000")

        try:
            port = int(port_str)
        except ValueError:
            port = 8000

        global_server = Server(host=host, port=port)
    return global_server

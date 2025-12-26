"""
Cookie服务模块
负责从多种来源获取、缓存和管理QZone的Cookie。
"""

from collections.abc import Callable
from pathlib import Path

import aiohttp
import orjson

from src.common.logger import get_logger
from src.plugin_system.apis import send_api

logger = get_logger("MaiZone.CookieService")


class CookieService:
    """
    管理Cookie的获取和缓存，支持多种获取策略。
    """

    def __init__(self, get_config: Callable):
        self.get_config = get_config
        self.cookie_dir = Path(__file__).resolve().parent.parent / "cookies"
        self.cookie_dir.mkdir(exist_ok=True)

    def _get_cookie_file_path(self, qq_account: str) -> Path:
        """获取指定QQ账号的cookie文件路径"""
        return self.cookie_dir / f"cookies-{qq_account}.json"

    def _save_cookies_to_file(self, qq_account: str, cookies: dict[str, str]):
        """将Cookie保存到本地文件"""
        cookie_file_path = self._get_cookie_file_path(qq_account)
        try:
            with open(cookie_file_path, "w", encoding="utf-8") as f:
                f.write(orjson.dumps(cookies, option=orjson.OPT_INDENT_2).decode("utf-8"))
            logger.info(f"Cookie已成功缓存至: {cookie_file_path}")
        except OSError as e:
            logger.error(f"无法写入Cookie文件 {cookie_file_path}: {e}")

    def _load_cookies_from_file(self, qq_account: str) -> dict[str, str] | None:
        """从本地文件加载Cookie"""
        cookie_file_path = self._get_cookie_file_path(qq_account)
        if cookie_file_path.exists():
            try:
                with open(cookie_file_path, encoding="utf-8") as f:
                    return orjson.loads(f.read())
            except (OSError, orjson.JSONDecodeError) as e:
                logger.error(f"无法读取或解析Cookie文件 {cookie_file_path}: {e}")
        return None

    async def _get_cookies_from_adapter(self, stream_id: str | None) -> dict[str, str] | None:
        """通过Adapter API获取Cookie"""
        try:
            params = {"domain": "user.qzone.qq.com"}
            if stream_id:
                response = await send_api.adapter_command_to_stream(
                    action="get_cookies", params=params, platform="qq", stream_id=stream_id, timeout=40.0
                )
            else:
                response = await send_api.adapter_command_to_stream(
                    action="get_cookies", params=params, platform="qq", timeout=40.0
                )

            if response and response.get("status") == "ok":
                cookie_str = response.get("data", {}).get("cookies", "")
                if cookie_str:
                    return {
                        k.strip(): v.strip() for k, v in (p.split("=", 1) for p in cookie_str.split("; ") if "=" in p)
                    }
        except Exception as e:
            logger.error(f"通过Adapter获取Cookie时发生异常: {e}")
        return None

    async def _get_cookies_from_http(self) -> dict[str, str] | None:
        """通过备用HTTP端点获取Cookie（带Token认证）"""
        host = self.get_config("cookie.http_fallback_host", "")
        port = self.get_config("cookie.http_fallback_port", "")
        napcat_token = self.get_config("cookie.napcat_token", "")

        if not host or not port:
            logger.debug("Cookie HTTP备用配置未设置，跳过HTTP方式。")
            return None

        http_url = f"http://{host}:{port}/get_cookies"

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            payload = {"domain": "user.qzone.qq.com"}

            # 构建请求头，包含Token认证
            headers = {"Content-Type": "application/json"}
            if napcat_token:
                headers["Authorization"] = f"Bearer {napcat_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(http_url, json=payload, headers=headers, timeout=timeout) as response:
                    if response.status == 403:
                        logger.debug("HTTP备用地址返回403 Forbidden，可能需要配置napcat_token。")
                        return None

                    response.raise_for_status()
                    data = await response.json()

                    # 确保返回的数据格式被正确解析，兼容Adapter的返回结构
                    cookie_str = data.get("data", {}).get("cookies")
                    if cookie_str and isinstance(cookie_str, str):
                        logger.info("从HTTP备用地址成功获取Cookie。")
                        return {
                            k.strip(): v.strip()
                            for k, v in (p.split("=", 1) for p in cookie_str.split("; ") if "=" in p)
                        }

                    logger.warning("从HTTP备用地址获取的Cookie格式不正确或为空。")
                    return None
        except aiohttp.ClientError as e:
            logger.debug(f"通过HTTP备用地址获取Cookie失败: {e}")
        except Exception as e:
            logger.warning(f"通过HTTP备用地址获取Cookie时发生异常: {e}")
        return None

    async def get_cookies(self, qq_account: str, stream_id: str | None) -> dict[str, str] | None:
        """
        获取Cookie，按以下顺序尝试：
        1. 本地文件缓存（优先，避免不必要的网络请求）
        2. HTTP备用端点
        3. Adapter API（最可靠，作为最后手段）
        """
        # 1. 优先尝试从本地文件加载（最快）
        cookies = self._load_cookies_from_file(qq_account)
        if cookies:
            logger.info("从本地缓存加载Cookie成功。")
            return cookies

        # 2. 尝试从HTTP备用端点获取
        logger.info("本地缓存不存在，尝试HTTP备用地址...")
        cookies = await self._get_cookies_from_http()
        if cookies:
            logger.info("从HTTP备用地址获取Cookie成功。")
            self._save_cookies_to_file(qq_account, cookies)
            return cookies

        # 3. 尝试从Adapter获取（最可靠的方式）
        logger.info("HTTP方式失败，尝试Adapter API...")
        cookies = await self._get_cookies_from_adapter(stream_id)
        if cookies:
            logger.info("从Adapter API获取Cookie成功。")
            self._save_cookies_to_file(qq_account, cookies)
            return cookies

        logger.error(
            f"为 {qq_account} 获取Cookie的所有方法均失败。"
            f"请确保Adapter连接正常，或配置HTTP备用地址，或存在有效的本地Cookie缓存。"
        )
        return None

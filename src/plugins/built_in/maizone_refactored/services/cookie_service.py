"""
Cookie服务模块（不使用本地缓存，每次都重新获取）
"""

from collections.abc import Callable
from pathlib import Path
from time import time

import aiohttp
import orjson

from src.common.logger import get_logger
from src.plugin_system.apis import send_api

logger = get_logger("MaiZone.CookieService")


class CookieService:
    """
    管理Cookie的获取（不使用本地缓存，每次都从HTTP或Adapter获取）。
    """

    def __init__(self, get_config: Callable):
        self.get_config = get_config
        self.cookie_dir = Path(__file__).resolve().parent.parent / "cookies"
        self.cookie_dir.mkdir(exist_ok=True)

    def _get_cookie_file_path(self, qq_account: str) -> Path:
        return self.cookie_dir / f"cookies-{qq_account}.json"

    async def _get_cookies_from_adapter(self, stream_id: str | None) -> dict[str, str] | None:
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
        不使用本地缓存：每次优先尝试 HTTP 备用端点，失败则调用 Adapter。
        """
        logger.info("始终从网络获取Cookie：尝试HTTP备用地址...")
        cookies = await self._get_cookies_from_http()
        if cookies:
            logger.info("从HTTP备用地址获取Cookie成功。")
            return cookies

        logger.info("HTTP方式失败，尝试Adapter API...")
        cookies = await self._get_cookies_from_adapter(stream_id)
        if cookies:
            logger.info("从Adapter API获取Cookie成功。")
            return cookies

        logger.error(f"为 {qq_account} 获取Cookie的所有方法均失败。")
        return None

    async def refresh_cookies(self, qq_account: str | None = None) -> dict | None:
        """
        强制刷新指定账号或所有账号的Cookie（不保存到本地）。
        返回单账号时为 dict 或 None；多账号返回 {account: dict|None}。
        """
        results: dict[str, dict | None] = {}

        accounts: list[str] = []
        if qq_account:
            accounts = [qq_account]
        else:
            cfg_accounts = self.get_config("cookie.auto_refresh_accounts", [])
            if isinstance(cfg_accounts, (list, tuple)) and cfg_accounts:
                accounts = [str(a) for a in cfg_accounts]
            else:
                for p in self.cookie_dir.glob("cookies-*.json"):
                    name = p.name
                    if name.startswith("cookies-") and name.endswith(".json"):
                        accounts.append(name[len("cookies-"):-len(".json")])

        if not accounts:
            logger.info("没有找到需要自动刷新的Cookie账号。")
            return {} if qq_account is None else None

        for acc in accounts:
            try:
                logger.info(f"开始强制刷新Cookie: {acc}")
                cookies = await self._get_cookies_from_http()
                if not cookies:
                    cookies = await self._get_cookies_from_adapter(None)
                if cookies:
                    logger.info(f"为 {acc} 刷新Cookie成功（未缓存）。")
                    results[acc] = cookies
                else:
                    logger.warning(f"为 {acc} 刷新Cookie失败。")
                    results[acc] = None
            except Exception as e:
                logger.exception(f"刷新 {acc} Cookie 时出现异常: {e}")
                results[acc] = None

        if qq_account:
            return results.get(qq_account)
        return results

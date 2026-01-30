"""
QQ空间服务模块
封装了所有与QQ空间API的直接交互，是插件的核心业务逻辑层。
"""

import asyncio
import base64
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiofiles
import aiohttp
import bs4
import json5
import orjson

from src.common.logger import get_logger
from src.plugin_system.apis import config_api, cross_context_api, person_api

from .content_service import ContentService
from .cookie_service import CookieService
from .image_service import ImageService
from .reply_tracker_service import ReplyTrackerService

logger = get_logger("MaiZone.QZoneService")


class QZoneService:
    """
    QQ空间服务类，负责所有API交互和业务流程编排。
    """

    # --- API Endpoints ---
    ZONE_LIST_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
    EMOTION_PUBLISH_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
    DOLIKE_URL = "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
    COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    LIST_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
    REPLY_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"

    def __init__(
        self,
        get_config: Callable,
        content_service: ContentService,
        image_service: ImageService,
        cookie_service: CookieService,
        reply_tracker: ReplyTrackerService | None = None,
    ):
        self.get_config = get_config
        self.content_service = content_service
        self.image_service = image_service
        self.cookie_service = cookie_service
        # 如果没有提供 reply_tracker 实例，则创建一个新的
        self.reply_tracker = reply_tracker if reply_tracker is not None else ReplyTrackerService()
        # 用于防止并发回复/评论的内存锁
        self.processing_comments = set()

    # --- Public Methods (High-Level Business Logic) ---
    async def _get_cross_context(self) -> str:
        """获取并构建跨群聊上下文"""
        context = ""
        user_id = self.get_config("cross_context.user_id")

        if user_id:
            logger.info(f"检测到互通组用户ID: {user_id}，准备获取上下文...")
            try:
                context = await cross_context_api.build_cross_context_for_user(
                    user_id=user_id,
                    platform="QQ",  # 硬编码为QQ
                    limit_per_stream=10,
                    stream_limit=3,
                )
                if context:
                    logger.info("成功获取到互通组上下文。")
                else:
                    logger.info("未获取到有效的互通组上下文。")
            except Exception as e:
                logger.error(f"获取互通组上下文时发生异常: {e}")
        return context

    async def _execute_api_call(self, func: Callable, *args, **kwargs) -> Any:
        """
        统一执行API调用，包含Cookie失效自动重试机制
        :param func: 要执行的API函数，该函数第一个参数必须是 api_client
        :param args: 传递给 func 的其他位置参数
        :param kwargs: 传递给 func 的关键字参数
        :return: func 的返回值
        """
        qq_account = config_api.get_global_config("bot.qq_account", "")
        # 从kwargs中提取stream_id，如果不存在则为None
        stream_id = kwargs.pop("stream_id", None)

        for retry_count in range(2):
            api_client = await self._get_api_client(qq_account, stream_id)
            if not api_client:
                raise RuntimeError("获取QZone API客户端失败")

            try:
                # 将 api_client 作为第一个参数传递给 func
                return await func(api_client, *args, **kwargs)
            except RuntimeError as e:
                if "错误码: -3000" in str(e) and retry_count == 0:
                    logger.warning("检测到Cookie失效（-3000错误），准备清除缓存并重试...")
                    self.cookie_service.clear_cache(qq_account)
                    continue
                raise
            except Exception:
                raise

    async def send_feed(self, topic: str, stream_id: str | None) -> dict[str, Any]:
        """发送一条说说（支持AI配图）"""
        cross_context = await self._get_cross_context()

        # 检查是否启用AI配图
        ai_image_enabled = self.get_config("ai_image.enable_ai_image", False)
        provider = self.get_config("ai_image.provider", "siliconflow")

        image_path = None

        if ai_image_enabled:
            # 启用AI配图：文本模型生成说说+图片提示词
            story, image_info = await self.content_service.generate_story_with_image_info(topic, context=cross_context)
            if not story:
                return {"success": False, "message": "生成说说内容失败"}

            # 根据provider调用对应的生图服务
            if provider == "novelai":
                try:
                    from .novelai_service import MaiZoneNovelAIService
                    novelai_service = MaiZoneNovelAIService(self.get_config)

                    if novelai_service.is_available():
                        # 解析画幅
                        aspect_ratio = image_info.get("aspect_ratio", "方图")
                        size_map = {
                            "方图": (1024, 1024),
                            "横图": (1216, 832),
                            "竖图": (832, 1216),
                        }
                        width, height = size_map.get(aspect_ratio, (1024, 1024))

                        logger.info("🎨 开始生成NovelAI配图...")
                        success, img_path, msg = await novelai_service.generate_image_from_prompt_data(
                            prompt=image_info.get("prompt", ""),
                            negative_prompt=image_info.get("negative_prompt"),
                            include_character=image_info.get("include_character", False),
                            width=width,
                            height=height
                        )

                        if success and img_path:
                            image_path = img_path
                            logger.info("✅ NovelAI配图生成成功")
                        else:
                            logger.warning(f"⚠️ NovelAI配图生成失败: {msg}")
                    else:
                        logger.warning("NovelAI服务不可用（未配置API Key）")

                except Exception as e:
                    logger.error(f"NovelAI配图生成出错: {e}", exc_info=True)

            elif provider == "siliconflow":
                try:
                    # 调用硅基流动生成图片
                    success, img_path = await self.image_service.generate_image_from_prompt(
                        prompt=image_info.get("prompt", ""),
                        save_dir=None  # 使用默认images目录
                    )
                    if success and img_path:
                        image_path = img_path
                        logger.info("✅ 硅基流动配图生成成功")
                    else:
                        logger.warning("⚠️ 硅基流动配图生成失败")
                except Exception as e:
                    logger.error(f"硅基流动配图生成出错: {e}", exc_info=True)
        else:
            # 不使用AI配图：只生成说说文本
            story = await self.content_service.generate_story(topic, context=cross_context)
            if not story:
                return {"success": False, "message": "生成说说内容失败"}

        # 加载图片
        images_bytes = []
        if image_path and image_path.exists():
            try:
                with open(image_path, "rb") as f:
                    images_bytes.append(f.read())
                logger.info("添加AI配图到说说")
            except Exception as e:
                logger.error(f"读取AI配图失败: {e}")

        async def _do_publish(api_client, content, images):
            success, _ = await api_client["publish"](content, images)
            if success:
                return {"success": True, "message": content}
            return {"success": False, "message": "发布说说至QQ空间失败"}

        try:
            return await self._execute_api_call(_do_publish, story, images_bytes, stream_id=stream_id)
        except Exception as e:
            logger.error(f"发布说说时发生异常: {e}")
            return {"success": False, "message": f"发布说说异常: {e}"}

    async def send_feed_from_activity(self, activity: str) -> dict[str, Any]:
        """根据日程活动发送一条说说"""
        cross_context = await self._get_cross_context()
        story = await self.content_service.generate_story_from_activity(activity, context=cross_context)
        if not story:
            return {"success": False, "message": "根据活动生成说说内容失败"}

        if self.get_config("send.enable_ai_image", False):
            await self.image_service.generate_images_for_story(story)

        async def _do_publish(api_client, content):
            success, _ = await api_client["publish"](content, [])
            if success:
                return {"success": True, "message": content}
            return {"success": False, "message": "发布说说至QQ空间失败"}

        try:
            return await self._execute_api_call(_do_publish, story, stream_id=None)
        except Exception as e:
            logger.error(f"根据活动发布说说时发生异常: {e}")
            return {"success": False, "message": f"发布说说异常: {e}"}

    async def read_and_process_feeds(self, target_name: str, stream_id: str | None) -> dict[str, Any]:
        """读取并处理指定好友的说说"""
        # 判断输入是QQ号还是昵称
        target_qq = None

        if target_name.isdigit():
            # 输入是纯数字，当作QQ号处理
            target_qq = int(target_name)
        else:
            # 输入是昵称，查询person_info获取QQ号
            target_person_id = await person_api.get_person_id_by_name(target_name)
            if not target_person_id:
                return {"success": False, "message": f"找不到名为'{target_name}'的好友"}
            person_info = await person_api.get_person_info(target_person_id)
            target_qq = person_info.get("user_id")
            if not target_qq:
                return {"success": False, "message": f"好友'{target_name}'没有关联QQ号"}

        num_to_read = self.get_config("read.read_number", 5)

        async def _do_read_process(api_client, t_qq, t_name, num):
            logger.debug(f"开始调用 list_feeds，target_qq={t_qq}, num={num}")
            feeds = await api_client["list_feeds"](t_qq, num)
            logger.debug(f"list_feeds 返回，feeds数量={len(feeds) if feeds else 0}")
            if not feeds:
                return {"success": True, "message": f"没有从'{t_name}'的空间获取到新说说。"}

            logger.debug(f"准备处理 {len(feeds)} 条说说")
            total_liked = 0
            total_commented = 0
            for feed in feeds:
                result = await self._process_single_feed(feed, api_client, str(t_qq), t_name)
                if result["liked"]:
                    total_liked += 1
                if result["commented"]:
                    total_commented += 1
                await asyncio.sleep(random.uniform(3, 7))

            # 构建详细的反馈信息
            stats_parts = []
            if total_liked > 0:
                stats_parts.append(f"点赞了{total_liked}条")
            if total_commented > 0:
                stats_parts.append(f"评论了{total_commented}条")

            if stats_parts:
                stats_msg = "、".join(stats_parts)
                message = f"成功查看了'{t_name}'的空间，{stats_msg}。"
            else:
                message = f"成功查看了'{t_name}'的 {len(feeds)} 条说说，但这次没有进行互动。"

            return {
                "success": True,
                "message": message,
                "stats": {"total": len(feeds), "liked": total_liked, "commented": total_commented},
            }

        try:
            return await self._execute_api_call(
                _do_read_process, target_qq, target_name, num_to_read, stream_id=stream_id
            )
        except Exception as e:
            logger.error(f"读取和处理说说时发生异常: {e}")
            return {"success": False, "message": f"处理说说时出现异常: {e}"}

    async def monitor_feeds(self, stream_id: str | None = None):
        """监控并处理所有好友的动态，包括回复自己说说的评论"""
        logger.info("开始执行好友动态监控...")
        qq_account = config_api.get_global_config("bot.qq_account", "")

        # 尝试执行，如果Cookie失效则自动重试一次
        for retry_count in range(2):  # 最多尝试2次
            api_client = await self._get_api_client(qq_account, stream_id)
            if not api_client:
                logger.error("监控失败：无法获取API客户端")
                return

            try:
                # --- 第一步: 单独处理自己说说的评论 ---
                if self.get_config("monitor.enable_auto_reply", False):
                    try:
                        # 传入新参数，表明正在检查自己的说说
                        own_feeds = await api_client["list_feeds"](qq_account, 5)
                        if own_feeds:
                            logger.info(f"获取到自己 {len(own_feeds)} 条说说，检查评论...")
                            for feed in own_feeds:
                                await self._reply_to_own_feed_comments(feed, api_client)
                                await asyncio.sleep(random.uniform(3, 5))
                    except Exception as e:
                        # 如果是Cookie失效，重新抛出以触发外层重试
                        if "错误码: -3000" in str(e):
                            raise
                        logger.error(f"处理自己说说评论时发生异常: {e}")

                # --- 第二步: 处理好友的动态 ---
                friend_feeds = await api_client["monitor_list_feeds"](20)
                if not friend_feeds:
                    logger.info("监控完成：未发现好友新说说")
                    return

                logger.info(f"监控任务: 发现 {len(friend_feeds)} 条好友新动态，准备处理...")
                monitor_stats = {"total": 0, "liked": 0, "commented": 0}
                for feed in friend_feeds:
                    target_qq = feed.get("target_qq")
                    if not target_qq or str(target_qq) == str(qq_account):  # 确保不重复处理自己的
                        continue

                    result = await self._process_single_feed(feed, api_client, str(target_qq), str(target_qq))
                    monitor_stats["total"] += 1
                    if result.get("liked"):
                        monitor_stats["liked"] += 1
                    if result.get("commented"):
                        monitor_stats["commented"] += 1
                    await asyncio.sleep(random.uniform(5, 10))

                logger.info(
                    f"监控任务完成: 处理了{monitor_stats['total']}条动态，"
                    f"点赞{monitor_stats['liked']}条，评论{monitor_stats['commented']}条"
                )
                return  # 成功完成，直接返回

            except RuntimeError as e:
                # QQ空间API返回的业务错误
                error_msg = str(e)

                # 检查是否是Cookie失效（-3000错误）
                if "错误码: -3000" in error_msg and retry_count == 0:
                    logger.warning("检测到Cookie失效（-3000错误），准备删除缓存并重试...")

                    # 删除Cookie缓存文件
                    cookie_file = self.cookie_service._get_cookie_file_path(qq_account)
                    if cookie_file.exists():
                        try:
                            cookie_file.unlink()
                            logger.info(f"已删除过期的Cookie缓存文件: {cookie_file}")
                        except Exception as delete_error:
                            logger.error(f"删除Cookie文件失败: {delete_error}")

                    # 重新获取API客户端会在下一次循环中自动进行
                    logger.info("Cookie已删除，正在重试...")
                    continue  # 继续循环，重试一次

                # 其他业务错误或重试后仍失败
                logger.error(f"监控好友动态时发生业务错误: {e}")
                return

            except Exception as e:
                # 其他未知异常
                logger.error(f"监控好友动态时发生异常: {e}")
                return

    # --- Internal Helper Methods ---


    async def _reply_to_own_feed_comments(self, feed: dict, api_client: dict):
        """处理对自己说说的评论并进行回复"""
        qq_account = config_api.get_global_config("bot.qq_account", "")
        comments = feed.get("comments", [])
        content = feed.get("content", "")
        fid = feed.get("tid", "")
        images = feed.get("images", [])  # 获取说说中的图片
        story_time = feed.get("created_time", "")  # 获取说说发送时间

        if not comments or not fid:
            return

        # 1. 将评论分为用户评论和自己的回复
        user_comments = [c for c in comments if str(c.get("qq_account")) != str(qq_account)]

        if not user_comments:
            return

        # 直接检查评论是否已回复，不做验证清理
        comments_to_process = []
        for comment in user_comments:
            comment_tid = comment.get("comment_tid")
            if not comment_tid:
                continue

            comment_key = f"{fid}_{comment_tid}"
            # 检查持久化记录和内存锁
            if not self.reply_tracker.has_replied(fid, comment_tid) and comment_key not in self.processing_comments:
                logger.debug(f"锁定待回复评论: {comment_key}")
                self.processing_comments.add(comment_key)
                comments_to_process.append(comment)

        if not comments_to_process:
            logger.debug(f"说说 {fid} 下的所有评论都已回复过或正在处理中")
            return

        logger.info(f"发现自己说说下的 {len(comments_to_process)} 条新评论，准备回复...")
        for comment in comments_to_process:
            comment_tid = comment.get("comment_tid")
            comment_key = f"{fid}_{comment_tid}"
            nickname = comment.get("nickname", "")
            comment_content = comment.get("content", "")
            commenter_qq = str(comment.get("qq_account", "")) if comment.get("qq_account") else None
            comment_time = comment.get("create_time", "")  # 获取评论时间

            try:
                reply_content = await self.content_service.generate_comment_reply(
                    story_content=content,
                    story_time=story_time,  # 传递说说发送时间
                    comment_content=comment_content,
                    comment_time=comment_time,  # 传递评论时间
                    commenter_name=nickname,
                    commenter_qq=commenter_qq,
                    images=images,  # 传递说说中的图片
                )
                if reply_content:
                    success = await api_client["reply"](fid, qq_account, nickname, reply_content, comment_tid)
                    if success:
                        self.reply_tracker.mark_as_replied(fid, comment_tid)
                        logger.info(f"成功回复'{nickname}'的评论: '{reply_content}'")
                    else:
                        logger.error(f"回复'{nickname}'的评论失败")
                    await asyncio.sleep(random.uniform(10, 20))
                else:
                    logger.warning(f"生成回复内容失败，跳过回复'{nickname}'的评论")
            except Exception as e:
                logger.error(f"回复'{nickname}'的评论时发生异常: {e}")
            finally:
                # 无论成功与否，都解除锁定
                logger.debug(f"解锁评论: {comment_key}")
                if comment_key in self.processing_comments:
                    self.processing_comments.remove(comment_key)

    async def _validate_and_cleanup_reply_records(self, fid: str, my_replies: list[dict]):
        """验证并清理已删除的回复记录"""
        # 获取当前记录中该说说的所有已回复评论ID
        recorded_replied_comments = self.reply_tracker.get_replied_comments(fid)

        if not recorded_replied_comments:
            return

        # 从API返回的我的回复中提取parent_tid（即被回复的评论ID）
        current_replied_comments = set()
        for reply in my_replies:
            parent_tid = reply.get("parent_tid")
            if parent_tid:
                current_replied_comments.add(parent_tid)

        # 找出记录中有但实际已不存在的回复
        deleted_replies = recorded_replied_comments - current_replied_comments

        if deleted_replies:
            logger.info(f"检测到 {len(deleted_replies)} 个回复已被删除，清理记录...")
            for comment_tid in deleted_replies:
                self.reply_tracker.remove_reply_record(fid, comment_tid)
                logger.debug(f"已清理删除的回复记录: feed_id={fid}, comment_id={comment_tid}")

    async def _process_single_feed(self, feed: dict, api_client: dict, target_qq: str, target_name: str) -> dict:
        """处理单条说说，决定是否评论和点赞

        返回:
            dict: {"liked": bool, "commented": bool}
        """
        content = feed.get("content", "")
        fid = feed.get("tid", "")
        # 正确提取转发内容（rt_con 可能是字典或字符串）
        rt_con = feed.get("rt_con", {}).get("content", "") if isinstance(feed.get("rt_con"), dict) else feed.get("rt_con", "")
        images = feed.get("images", [])

        result = {"liked": False, "commented": False}

        # --- 处理评论 ---
        comment_key = f"{fid}_main_comment"
        should_comment = random.random() <= self.get_config("read.comment_possibility", 0.3)

        if (
            should_comment
            and not self.reply_tracker.has_replied(fid, "main_comment")
            and comment_key not in self.processing_comments
        ):
            logger.debug(f"锁定待评论说说: {comment_key}")
            self.processing_comments.add(comment_key)
            try:
                # 使用空间专用评论方法
                comment_text = await self.content_service.generate_qzone_comment(
                    target_name=target_name,
                    content=content or rt_con or "说说内容",
                    rt_con=rt_con if content else None,
                    images=images,
                    target_qq=target_qq,
                )
                if comment_text:
                    success = await api_client["comment"](target_qq, fid, comment_text)
                    if success:
                        self.reply_tracker.mark_as_replied(fid, "main_comment")
                        logger.info(f"成功评论'{target_name}'的说说: '{comment_text}'")
                        result["commented"] = True
                    else:
                        logger.error(f"评论'{target_name}'的说说失败")
            except Exception as e:
                # 如果是Cookie失效，重新抛出以触发外层重试
                if "错误码: -3000" in str(e):
                    raise
                logger.error(f"评论'{target_name}'的说说时发生异常: {e}")
            finally:
                logger.debug(f"解锁说说: {comment_key}")
                if comment_key in self.processing_comments:
                    self.processing_comments.remove(comment_key)

        # --- 处理点赞 (逻辑不变) ---
        like_probability = self.get_config("read.like_possibility", 1.0)
        if random.random() <= like_probability:
            logger.info(f"准备点赞说说: target_qq={target_qq}, fid={fid}")
            like_success = await api_client["like"](target_qq, fid)
            if like_success:
                logger.info(f"成功点赞'{target_name}'的说说: fid={fid}")
                result["liked"] = True
            else:
                logger.warning(f"点赞'{target_name}'的说说失败: fid={fid}")
        else:
            logger.debug(f"概率未命中，跳过点赞: probability={like_probability}")

        return result

    def _generate_gtk(self, skey: str) -> str:
        hash_val = 5381
        for char in skey:
            hash_val += (hash_val << 5) + ord(char)
        return str(hash_val & 2147483647)

    async def _renew_and_load_cookies(self, qq_account: str, stream_id: str | None) -> dict[str, str] | None:
        cookie_dir = Path(__file__).resolve().parent.parent / "cookies"
        cookie_dir.mkdir(exist_ok=True)
        cookie_file_path = cookie_dir / f"cookies-{qq_account}.json"

        # 优先尝试通过Napcat HTTP服务获取最新的Cookie
        try:
            logger.info("尝试通过Napcat HTTP服务获取Cookie...")
            host = self.get_config("cookie.http_fallback_host", "172.20.130.55")
            port = self.get_config("cookie.http_fallback_port", "9999")
            napcat_token = self.get_config("cookie.napcat_token", "")

            cookie_data = await self._fetch_cookies_http(host, port, napcat_token)
            if cookie_data and "cookies" in cookie_data:
                cookie_str = cookie_data["cookies"]
                parsed_cookies = {
                    k.strip(): v.strip() for k, v in (p.split("=", 1) for p in cookie_str.split("; ") if "=" in p)
                }
                # 成功获取后，异步写入本地文件作为备份
                try:
                    async with aiofiles.open(cookie_file_path, "wb") as f:
                        await f.write(orjson.dumps(parsed_cookies))
                    logger.info(f"通过Napcat服务成功更新Cookie，并已保存至: {cookie_file_path}")
                except Exception as e:
                    logger.warning(f"保存Cookie到文件时出错: {e}")
                return parsed_cookies
            else:
                logger.warning("通过Napcat服务未能获取有效Cookie。")

        except Exception as e:
            logger.warning(f"通过Napcat HTTP服务获取Cookie时发生异常: {e}。将尝试从本地文件加载。")

        # 如果通过服务获取失败，则尝试从本地文件加载
        logger.info("尝试从本地Cookie文件加载...")
        if cookie_file_path.exists():
            try:
                async with aiofiles.open(cookie_file_path, "rb") as f:
                    content = await f.read()
                    cookies = orjson.loads(content)
                    logger.info(f"成功从本地文件加载Cookie: {cookie_file_path}")
                    return cookies
            except Exception as e:
                logger.error(f"从本地文件 {cookie_file_path} 读取或解析Cookie失败: {e}")
        else:
            logger.warning(f"本地Cookie文件不存在: {cookie_file_path}")

        logger.error("所有获取Cookie的方式均失败。")
        return None

    async def _fetch_cookies_http(self, host: str, port: int, napcat_token: str) -> dict | None:
        """通过HTTP服务器获取Cookie"""
        # 从配置中读取主机和端口，如果未提供则使用传入的参数
        final_host = self.get_config("cookie.http_fallback_host", host)
        final_port = self.get_config("cookie.http_fallback_port", port)
        url = f"http://{final_host}:{final_port}/get_cookies"

        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                headers = {"Content-Type": "application/json"}
                if napcat_token:
                    headers["Authorization"] = f"Bearer {napcat_token}"

                payload = {"domain": "user.qzone.qq.com"}

                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30.0)) as session:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        resp.raise_for_status()

                        if resp.status != 200:
                            error_msg = f"Napcat服务返回错误状态码: {resp.status}"
                            if resp.status == 403:
                                error_msg += " (Token验证失败)"
                            raise RuntimeError(error_msg)

                        data = await resp.json()
                        if data.get("status") != "ok" or "cookies" not in data.get("data", {}):
                            raise RuntimeError(f"获取 cookie 失败: {data}")
                        return data["data"]

            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"无法连接到Napcat服务(尝试 {attempt + 1}/{max_retries}): {url}，错误: {e!s}")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                logger.error(f"无法连接到Napcat服务(最终尝试): {url}，错误: {e!s}")
                raise RuntimeError(f"无法连接到Napcat服务: {url}") from e
            except Exception as e:
                logger.error(f"获取cookie异常: {e!s}")
                raise

        raise RuntimeError(f"无法连接到Napcat服务: 超过最大重试次数({max_retries})")

    async def _get_api_client(self, qq_account: str, stream_id: str | None) -> dict | None:
        logger.debug(f"开始获取API客户端，qq_account={qq_account}")
        cookies = await self.cookie_service.get_cookies(qq_account, stream_id)
        if not cookies:
            logger.error(
                "获取API客户端失败：未能获取到Cookie。请检查Napcat连接是否正常，或是否存在有效的本地Cookie文件。"
            )
            return None

        logger.debug(f"Cookie获取成功，keys: {list(cookies.keys())}")

        p_skey = cookies.get("p_skey") or cookies.get("p_skey".upper())
        if not p_skey:
            logger.error(f"获取API客户端失败：Cookie中缺少关键的 'p_skey'。Cookie内容: {cookies}")
            return None

        logger.debug("p_skey获取成功")

        gtk = self._generate_gtk(p_skey)
        uin = cookies.get("uin", "").lstrip("o")
        if not uin:
            logger.error(f"获取API客户端失败：Cookie中缺少关键的 'uin'。Cookie内容: {cookies}")
            return None

        logger.debug(f"uin={uin}, gtk={gtk}, 准备构造API客户端")

        async def _request(method, url, params=None, data=None, headers=None):
            final_headers = {"referer": f"https://user.qzone.qq.com/{uin}", "origin": "https://user.qzone.qq.com"}
            if headers:
                final_headers.update(headers)

            async with aiohttp.ClientSession(cookies=cookies) as session:
                timeout = aiohttp.ClientTimeout(total=20)
                async with session.request(
                    method, url, params=params, data=data, headers=final_headers, timeout=timeout
                ) as response:
                    response.raise_for_status()
                    return await response.text()

        async def _publish(content: str, images: list[bytes]) -> tuple[bool, str]:
            """发布说说"""
            try:
                post_data = {
                    "syn_tweet_verson": "1",
                    "paramstr": "1",
                    "who": "1",
                    "con": content,
                    "feedversion": "1",
                    "ver": "1",
                    "ugc_right": "1",
                    "to_sign": "0",
                    "hostuin": uin,
                    "code_version": "1",
                    "format": "json",
                    "qzreferrer": f"https://user.qzone.qq.com/{uin}",
                }

                # 处理图片上传
                if images:
                    logger.info(f"开始上传 {len(images)} 张图片...")
                    pic_bos = []
                    richvals = []

                    for i, img_bytes in enumerate(images):
                        try:
                            # 上传图片到QQ空间
                            upload_result = await _upload_image(img_bytes, i)
                            if upload_result:
                                pic_bos.append(upload_result["pic_bo"])
                                richvals.append(upload_result["richval"])
                                logger.info(f"图片 {i + 1} 上传成功")
                            else:
                                logger.error(f"图片 {i + 1} 上传失败")
                        except Exception as e:
                            logger.error(f"上传图片 {i + 1} 时发生异常: {e}")

                    if pic_bos and richvals:
                        # 完全按照原版格式设置图片参数
                        post_data["pic_bo"] = ",".join(pic_bos)
                        post_data["richtype"] = "1"
                        post_data["richval"] = "\t".join(richvals)  # 原版使用制表符分隔

                        logger.info(f"准备发布带图说说: {len(pic_bos)} 张图片")
                        logger.info(f"pic_bo参数: {post_data['pic_bo']}")
                        logger.info(f"richval参数长度: {len(post_data['richval'])} 字符")
                    else:
                        logger.warning("所有图片上传失败，将发布纯文本说说")

                res_text = await _request("POST", self.EMOTION_PUBLISH_URL, params={"g_tk": gtk}, data=post_data)
                result = orjson.loads(res_text)

                if result.get("code") == -3000:
                    raise RuntimeError(f"发布说说失败: {result.get('message')} (错误码: -3000)")

                tid = result.get("tid", "")

                if tid:
                    if images and pic_bos:
                        logger.info(f"成功发布带图说说，tid: {tid}，包含 {len(pic_bos)} 张图片")
                    else:
                        logger.info(f"成功发布文本说说，tid: {tid}")
                else:
                    logger.error(f"发布说说失败，API返回: {result}")

                return bool(tid), tid
            except Exception as e:
                logger.error(f"发布说说异常: {e}")
                return False, ""

        def _image_to_base64(image_bytes: bytes) -> str:
            """将图片字节转换为base64字符串（仿照原版实现）"""
            pic_base64 = base64.b64encode(image_bytes)
            return str(pic_base64)[2:-1]  # 去掉 b'...' 的前缀和后缀

        def _get_picbo_and_richval(upload_result: dict) -> tuple:
            """从上传结果中提取图片的picbo和richval值（仿照原版实现）"""
            json_data = upload_result

            if "ret" not in json_data:
                raise Exception("获取图片picbo和richval失败")

            if json_data["ret"] != 0:
                raise Exception("上传图片失败")

            # 从URL中提取bo参数
            picbo_spt = json_data["data"]["url"].split("&bo=")
            if len(picbo_spt) < 2:
                raise Exception("上传图片失败")
            picbo = picbo_spt[1]

            # 构造richval - 完全按照原版格式
            richval = ",{},{},{},{},{},{},,{},{}".format(
                json_data["data"]["albumid"],
                json_data["data"]["lloc"],
                json_data["data"]["sloc"],
                json_data["data"]["type"],
                json_data["data"]["height"],
                json_data["data"]["width"],
                json_data["data"]["height"],
                json_data["data"]["width"],
            )

            return picbo, richval

        async def _upload_image(image_bytes: bytes, index: int) -> dict[str, str] | None:
            """上传图片到QQ空间（完全按照原版实现）"""
            try:
                upload_url = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"

                # 完全按照原版构建请求数据
                post_data = {
                    "filename": "filename",
                    "zzpanelkey": "",
                    "uploadtype": "1",
                    "albumtype": "7",
                    "exttype": "0",
                    "skey": cookies.get("skey", ""),
                    "zzpaneluin": uin,
                    "p_uin": uin,
                    "uin": uin,
                    "p_skey": cookies.get("p_skey", ""),
                    "output_type": "json",
                    "qzonetoken": "",
                    "refer": "shuoshuo",
                    "charset": "utf-8",
                    "output_charset": "utf-8",
                    "upload_hd": "1",
                    "hd_width": "2048",
                    "hd_height": "10000",
                    "hd_quality": "96",
                    "backUrls": "http://upbak.photo.qzone.qq.com/cgi-bin/upload/cgi_upload_image,"
                    "http://119.147.64.75/cgi-bin/upload/cgi_upload_image",
                    "url": f"https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image?g_tk={gtk}",
                    "base64": "1",
                    "picfile": _image_to_base64(image_bytes),
                }

                headers = {"referer": f"https://user.qzone.qq.com/{uin}", "origin": "https://user.qzone.qq.com"}

                logger.info(f"开始上传图片 {index + 1}...")

                async with aiohttp.ClientSession(cookies=cookies) as session:
                    timeout = aiohttp.ClientTimeout(total=60)
                    async with session.post(upload_url, data=post_data, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            resp_text = await response.text()
                            logger.info(f"图片上传响应状态码: {response.status}")
                            logger.info(f"图片上传响应内容前500字符: {resp_text[:500]}")

                            # 按照原版方式解析响应
                            start_idx = resp_text.find("{")
                            end_idx = resp_text.rfind("}") + 1
                            if start_idx != -1 and end_idx != -1:
                                json_str = resp_text[start_idx:end_idx]
                                try:
                                    upload_result = orjson.loads(json_str)
                                except orjson.JSONDecodeError:
                                    logger.error(f"图片上传响应JSON解析失败，原始响应: {resp_text}")
                                    return None

                                logger.debug(f"图片上传解析结果: {upload_result}")

                                if upload_result.get("ret") == 0:
                                    try:
                                        # 使用原版的参数提取逻辑
                                        picbo, richval = _get_picbo_and_richval(upload_result)
                                        logger.info(f"图片 {index + 1} 上传成功: picbo={picbo}")
                                        return {"pic_bo": picbo, "richval": richval}
                                    except Exception as e:
                                        logger.error(
                                            f"从上传结果中提取图片参数失败: {e}, 上传结果: {upload_result}",
                                            exc_info=True,
                                        )
                                        return None
                                else:
                                    logger.error(f"图片 {index + 1} 上传失败: {upload_result}")
                                    return None
                            else:
                                logger.error(f"无法从响应中提取JSON内容: {resp_text}")
                                return None
                        else:
                            error_text = await response.text()
                            logger.error(f"图片上传HTTP请求失败，状态码: {response.status}, 响应: {error_text[:200]}")
                            return None

            except Exception as e:
                logger.error(f"上传图片 {index + 1} 异常: {e}")
                return None

        async def _list_feeds(t_qq: str, num: int) -> list[dict]:
            """获取指定用户说说列表 (统一接口)"""
            try:
                logger.debug(f"_list_feeds 开始，t_qq={t_qq}, num={num}")
                # 统一使用 format=json 获取完整评论
                params = {
                    "g_tk": gtk,
                    "uin": t_qq,
                    "ftype": 0,
                    "sort": 0,
                    "pos": 0,
                    "num": num,
                    "replynum": 999,  # 尽量获取更多
                    "code_version": 1,
                    "format": "json",  # 关键：使用JSON格式
                    "need_comment": 1,
                }
                logger.debug(f"准备发送HTTP请求到 {self.LIST_URL}")
                res_text = await _request("GET", self.LIST_URL, params=params)
                logger.debug(f"HTTP请求返回，响应长度={len(res_text)}")
                json_data = orjson.loads(res_text)
                logger.debug(f"JSON解析成功，code={json_data.get('code')}")

                if json_data.get("code") != 0:
                    error_code = json_data.get("code")
                    error_message = json_data.get("message", "未知错误")
                    logger.warning(f"获取说说列表API返回错误: code={error_code}, message={error_message}")

                    # 将API错误信息抛出，让上层处理并反馈给用户
                    raise RuntimeError(f"QQ空间API错误: {error_message} (错误码: {error_code})")

                feeds_list = []
                my_name = json_data.get("logininfo", {}).get("name", "")
                total_msgs = len(json_data.get("msglist", []))
                logger.debug(f"[DEBUG] 从API获取到 {total_msgs} 条原始说说")

                for idx, msg in enumerate(json_data.get("msglist", [])):
                    msg_tid = msg.get("tid", "")
                    msg_content = msg.get("content", "")
                    msg_rt_con = msg.get("rt_con")
                    is_retweet = bool(msg_rt_con)

                    logger.debug(f"[DEBUG] 说说 {idx+1}/{total_msgs}: tid={msg_tid}, 是否转发={is_retweet}, content长度={len(msg_content)}")

                    # 当读取的是好友动态时，检查是否已评论过，如果是则跳过
                    is_friend_feed = str(t_qq) != str(uin)
                    if is_friend_feed:
                        commentlist_for_check = msg.get("commentlist")
                        is_commented = False
                        if isinstance(commentlist_for_check, list):
                            is_commented = any(
                                c.get("name") == my_name for c in commentlist_for_check if isinstance(c, dict)
                            )
                        if is_commented:
                            logger.debug(f"[DEBUG] 跳过已评论的说说: tid={msg_tid}, 是否转发={is_retweet}")
                            continue

                    # --- 安全地处理图片列表 ---
                    images = []
                    if "pic" in msg and isinstance(msg["pic"], list):
                        images = [pic.get("url1", "") for pic in msg["pic"] if pic.get("url1")]
                    elif "pictotal" in msg and isinstance(msg["pictotal"], list):
                        images = [pic.get("url1", "") for pic in msg["pictotal"] if pic.get("url1")]

                    # --- 解析完整评论列表 (包括二级评论) ---
                    comments = []
                    commentlist = msg.get("commentlist")

                    if isinstance(commentlist, list):
                        for c in commentlist:
                            if not isinstance(c, dict):
                                continue

                            # 解析评论时间（优先使用 createTime2，它是完整的格式化时间）
                            comment_create_time = ""
                            # 优先使用 createTime2（格式：YYYY-MM-DD HH:MM:SS）
                            if c.get("createTime2"):
                                comment_create_time = c.get("createTime2")
                            elif c.get("create_time"):
                                # create_time 是时间戳
                                raw_time = c.get("create_time")
                                try:
                                    if isinstance(raw_time, (int, float)):
                                        comment_create_time = time.strftime(
                                            "%Y-%m-%d %H:%M:%S", time.localtime(int(raw_time))
                                        )
                                    elif isinstance(raw_time, str) and raw_time.isdigit():
                                        comment_create_time = time.strftime(
                                            "%Y-%m-%d %H:%M:%S", time.localtime(int(raw_time))
                                        )
                                except (ValueError, TypeError):
                                    pass

                            # 添加主评论
                            comments.append(
                                {
                                    "qq_account": c.get("uin"),
                                    "nickname": c.get("name"),
                                    "content": c.get("content"),
                                    "comment_tid": c.get("tid"),
                                    "parent_tid": None,  # 主评论没有父ID
                                    "create_time": comment_create_time,  # 添加评论时间
                                }
                            )
                            # 检查并添加二级评论 (回复)
                            if "list_3" in c and isinstance(c["list_3"], list):
                                for reply in c["list_3"]:
                                    if not isinstance(reply, dict):
                                        continue

                                    # 解析二级评论时间（优先使用 createTime2）
                                    reply_create_time = ""
                                    if reply.get("createTime2"):
                                        reply_create_time = reply.get("createTime2")
                                    elif reply.get("create_time"):
                                        raw_time = reply.get("create_time")
                                        try:
                                            if isinstance(raw_time, (int, float)):
                                                reply_create_time = time.strftime(
                                                    "%Y-%m-%d %H:%M:%S", time.localtime(int(raw_time))
                                                )
                                            elif isinstance(raw_time, str) and raw_time.isdigit():
                                                reply_create_time = time.strftime(
                                                    "%Y-%m-%d %H:%M:%S", time.localtime(int(raw_time))
                                                )
                                        except (ValueError, TypeError):
                                            pass

                                    comments.append(
                                        {
                                            "qq_account": reply.get("uin"),
                                            "nickname": reply.get("name"),
                                            "content": reply.get("content"),
                                            "comment_tid": reply.get("tid"),
                                            "parent_tid": c.get("tid"),  # 父ID是主评论的ID
                                            "create_time": reply_create_time,  # 添加评论时间
                                        }
                                    )

                    feeds_list.append(
                        {
                            "tid": msg.get("tid", ""),
                            "content": msg.get("content", ""),
                            "created_time": time.strftime(
                                "%Y-%m-%d %H:%M:%S", time.localtime(msg.get("created_time", 0))
                            ),
                            "rt_con": msg.get("rt_con", {}).get("content", "")
                            if isinstance(msg.get("rt_con"), dict)
                            else "",
                            "images": images,
                            "comments": comments,
                        }
                    )

                logger.info(f"成功获取到 {len(feeds_list)} 条说说 from {t_qq} (使用统一JSON接口)")
                return feeds_list
            except RuntimeError:
                # QQ空间API业务错误，向上传播让调用者处理
                raise
            except Exception as e:
                # 其他异常（如网络错误、JSON解析错误等），记录后返回空列表
                logger.error(f"获取说说列表失败: {e}")
                return []

        async def _comment(t_qq: str, feed_id: str, text: str) -> bool:
            """评论说说"""
            try:
                data = {
                    "topicId": f"{t_qq}_{feed_id}__1",
                    "uin": uin,
                    "hostUin": t_qq,
                    "content": text,
                    "format": "fs",
                    "plat": "qzone",
                    "source": "ic",
                    "platformid": 52,
                    "ref": "feeds",
                }
                response_text = await _request("POST", self.COMMENT_URL, params={"g_tk": gtk}, data=data)

                # 解析响应检查业务状态
                try:
                    response_data = orjson.loads(response_text)
                    code = response_data.get("code", -1)
                    if code == 0:
                        logger.info(f"评论API返回成功: feed_id={feed_id}")
                        return True
                    else:
                        message = response_data.get("message", "未知错误")
                        if code == -3000:
                            raise RuntimeError(f"评论API返回失败: {message} (错误码: -3000)")
                        logger.error(f"评论API返回失败: code={code}, message={message}, feed_id={feed_id}")
                        return False
                except orjson.JSONDecodeError:
                    logger.warning(f"评论API响应无法解析为JSON，假定成功: {response_text[:200]}")
                    return True
            except Exception as e:
                if "错误码: -3000" in str(e):
                    raise
                logger.error(f"评论说说异常: {e}")
                return False

        async def _like(t_qq: str, feed_id: str) -> bool:
            """点赞说说"""
            try:
                data = {
                    "opuin": uin,
                    "unikey": f"http://user.qzone.qq.com/{t_qq}/mood/{feed_id}",
                    "curkey": f"http://user.qzone.qq.com/{t_qq}/mood/{feed_id}",
                    "from": 1,
                    "appid": 311,
                    "typeid": 0,
                    "abstime": int(time.time()),
                    "fid": feed_id,
                    "active": 0,
                    "format": "json",
                    "fupdate": 1,
                }
                response_text = await _request("POST", self.DOLIKE_URL, params={"g_tk": gtk}, data=data)

                # 解析响应检查业务状态
                try:
                    response_data = orjson.loads(response_text)
                    code = response_data.get("code", -1)
                    if code == 0:
                        logger.debug(f"点赞API返回成功: feed_id={feed_id}")
                        return True
                    else:
                        message = response_data.get("message", "未知错误")
                        if code == -3000:
                            raise RuntimeError(f"点赞API返回失败: {message} (错误码: -3000)")
                        logger.warning(f"点赞API返回失败: code={code}, message={message}, feed_id={feed_id}")
                        return False
                except orjson.JSONDecodeError:
                    logger.warning(f"点赞API响应无法解析为JSON，假定成功: {response_text[:200]}")
                    return True
            except Exception as e:
                if "错误码: -3000" in str(e):
                    raise
                logger.error(f"点赞说说异常: {e}")
                return False

        async def _reply(fid, host_qq, target_name, content, comment_tid):
            """回复评论 - 修复为能正确提醒的回复格式"""
            try:
                # 修复回复逻辑：确保能正确提醒被回复的人
                data = {
                    "topicId": f"{host_qq}_{fid}__1",
                    "parent_tid": comment_tid,
                    "uin": uin,
                    "hostUin": host_qq,
                    "content": content,
                    "format": "fs",
                    "plat": "qzone",
                    "source": "ic",
                    "platformid": 52,
                    "ref": "feeds",
                    "richtype": "",
                    "richval": "",
                    "paramstr": "",
                }

                # 记录详细的请求参数用于调试
                logger.info(
                    f"子回复请求参数: topicId={data['topicId']}, parent_tid={data['parent_tid']}, content='{content[:50]}...'"
                )

                response_text = await _request("POST", self.REPLY_URL, params={"g_tk": gtk}, data=data)

                # 解析响应检查业务状态
                try:
                    response_data = orjson.loads(response_text)
                    code = response_data.get("code", -1)
                    if code == 0:
                        logger.info(f"回复API返回成功: fid={fid}, parent_tid={comment_tid}")
                        return True
                    else:
                        message = response_data.get("message", "未知错误")
                        if code == -3000:
                            raise RuntimeError(f"回复API返回失败: {message} (错误码: -3000)")
                        logger.error(f"回复API返回失败: code={code}, message={message}, fid={fid}")
                        return False
                except orjson.JSONDecodeError:
                    logger.warning(f"回复API响应无法解析为JSON，假定成功: {response_text[:200]}")
                    return True
            except Exception as e:
                if "错误码: -3000" in str(e):
                    raise
                logger.error(f"回复评论异常: {e}")
                return False

        async def _monitor_list_feeds(num: int) -> list[dict]:
            """监控好友动态"""
            try:
                params = {
                    "uin": uin,
                    "scope": 0,
                    "view": 1,
                    "filter": "all",
                    "flag": 1,
                    "applist": "all",
                    "pagenum": 1,
                    "count": num,
                    "format": "json",
                    "g_tk": gtk,
                    "useutf8": 1,
                    "outputhtmlfeed": 1,
                }
                res_text = await _request("GET", self.ZONE_LIST_URL, params=params)

                # 处理不同的响应格式
                json_str = ""
                stripped_res_text = res_text.strip()
                if stripped_res_text.startswith("_Callback(") and stripped_res_text.endswith(");"):
                    json_str = stripped_res_text[len("_Callback(") : -2]
                elif stripped_res_text.startswith("{") and stripped_res_text.endswith("}"):
                    json_str = stripped_res_text
                else:
                    logger.warning(f"意外的响应格式: {res_text[:100]}...")
                    return []

                json_str = json_str.replace("undefined", "null").strip()

                # 解析JSON
                try:
                    json_data = json5.loads(json_str)
                except Exception as parse_error:
                    logger.error(f"JSON解析失败: {parse_error}, 原始数据: {json_str[:200]}...")
                    return []

                # 检查JSON数据类型
                if not isinstance(json_data, dict):
                    logger.warning(f"解析后的JSON数据不是字典类型: {type(json_data)}")
                    return []

                # 检查错误码（在try-except之外，让异常能向上传播）
                if json_data.get("code") != 0:
                    error_code = json_data.get("code")
                    error_msg = json_data.get("message", "未知错误")
                    logger.warning(f"QQ空间API返回错误: code={error_code}, message={error_msg}")
                    # 抛出异常以便上层的重试机制捕获
                    raise RuntimeError(f"QQ空间API错误: {error_msg} (错误码: {error_code})")

                feeds_data = []
                if isinstance(json_data, dict):
                    data_level1 = json_data.get("data")
                    if isinstance(data_level1, dict):
                        feeds_data = data_level1.get("data", [])

                feeds_list = []
                for feed in feeds_data:
                    if not feed or not isinstance(feed, dict):
                        continue

                    if str(feed.get("appid", "")) != "311":
                        continue

                    target_qq = str(feed.get("uin", ""))
                    tid = feed.get("key", "")
                    if not target_qq or not tid:
                        continue

                    if target_qq == str(uin):
                        continue

                    html_content = feed.get("html", "")
                    if not html_content:
                        continue

                    soup = bs4.BeautifulSoup(html_content, "html.parser")

                    like_btn = soup.find("a", class_="qz_like_btn_v3")
                    is_liked = False
                    if isinstance(like_btn, bs4.Tag) and like_btn.get("data-islike") == "1":
                        is_liked = True

                    if is_liked:
                        continue

                    text_div = soup.find("div", class_="f-info")
                    text = text_div.get_text(strip=True) if isinstance(text_div, bs4.Tag) else ""

                    # --- 借鉴原版插件的精确图片提取逻辑 ---
                    image_urls = []
                    img_box = soup.find("div", class_="img-box")
                    if isinstance(img_box, bs4.Tag):
                        for img in img_box.find_all("img"):
                            if isinstance(img, bs4.Tag):
                                src = img.get("src")
                                if src and isinstance(src, str) and "qzonestyle.gtimg.cn" not in src:
                                    image_urls.append(src)

                    # 视频封面也视为图片
                    video_thumb = soup.select_one("div.video-img img")
                    if isinstance(video_thumb, bs4.Tag) and "src" in video_thumb.attrs:
                        image_urls.append(video_thumb["src"])

                    # 去重
                    images = list(set(image_urls))

                    comments = []
                    comment_divs = soup.find_all("div", class_="f-single-comment")
                    for comment_div in comment_divs:
                        if not isinstance(comment_div, bs4.Tag):
                            continue
                        # --- 处理主评论 ---
                        author_a = comment_div.find("a", class_="f-nick")
                        content_span = comment_div.find("span", class_="f-re-con")

                        if isinstance(author_a, bs4.Tag) and isinstance(content_span, bs4.Tag):
                            comments.append(
                                {
                                    "qq_account": str(comment_div.get("data-uin", "")),
                                    "nickname": author_a.get_text(strip=True),
                                    "content": content_span.get_text(strip=True),
                                    "comment_tid": comment_div.get("data-tid", ""),
                                    "parent_tid": None,  # 主评论没有父ID
                                }
                            )

                        # --- 处理这条主评论下的所有回复 ---
                        reply_divs = comment_div.find_all("div", class_="f-single-re")
                        for reply_div in reply_divs:
                            if not isinstance(reply_div, bs4.Tag):
                                continue
                            reply_author_a = reply_div.find("a", class_="f-nick")
                            reply_content_span = reply_div.find("span", class_="f-re-con")

                            if isinstance(reply_author_a, bs4.Tag) and isinstance(reply_content_span, bs4.Tag):
                                comments.append(
                                    {
                                        "qq_account": str(reply_div.get("data-uin", "")),
                                        "nickname": reply_author_a.get_text(strip=True),
                                        "content": reply_content_span.get_text(strip=True).lstrip(
                                            ": "
                                        ),
                                        "comment_tid": reply_div.get("data-tid", ""),
                                        "parent_tid": reply_div.get(
                                            "data-parent-tid", comment_div.get("data-tid", "")
                                        ),
                                    }
                                )

                    feeds_list.append(
                        {"target_qq": target_qq, "tid": tid, "content": text, "images": images, "comments": comments}
                    )
                logger.info(f"监控任务发现 {len(feeds_list)} 条未处理的新说说。")
                return feeds_list
            except Exception as e:
                # 检查是否是Cookie失效错误（-3000），如果是则重新抛出
                if "错误码: -3000" in str(e):
                    logger.warning("监控任务遇到Cookie失效错误，重新抛出异常以触发上层重试")
                    raise  # 重新抛出异常，让上层处理
                logger.error(f"监控好友动态失败: {e}")
                return []

        logger.debug("API客户端构造完成，返回包含6个方法的字典")
        return {
            "publish": _publish,
            "list_feeds": _list_feeds,
            "comment": _comment,
            "like": _like,
            "reply": _reply,
            "monitor_list_feeds": _monitor_list_feeds,
        }

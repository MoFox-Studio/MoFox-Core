"""
时间解析器：将相对时间转换为绝对时间

支持的时间表达：
- 今天、明天、昨天、前天、后天
- X天前、X天后
- X小时前、X小时后
- 上周、上个月、去年
- 具体日期：2025-11-05, 11月5日
- 时间点：早上8点、下午3点、晚上9点
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from src.common.logger import get_logger

logger = get_logger(__name__)


class TimeParser:
    """
    时间解析器

    负责将自然语言时间表达转换为标准化的绝对时间
    """

    def __init__(self, reference_time: datetime | None = None):
        """
        初始化时间解析器

        Args:
            reference_time: 参考时间（通常是当前时间）
        """
        self.reference_time = reference_time or datetime.now()

    def parse(self, time_str: str) -> datetime | None:
        """
        解析时间字符串

        Args:
            time_str: 时间字符串

        Returns:
            标准化的datetime对象，如果解析失败则返回None
        """
        if not time_str or not isinstance(time_str, str):
            return None

        time_str = time_str.strip()

        # 先尝试组合解析（如"今天下午"、"昨天晚上"）
        combined_result = self._parse_combined_time(time_str)
        if combined_result:
            logger.debug(f"时间解析: '{time_str}' → {combined_result.isoformat()}")
            return combined_result

        # 尝试各种解析方法
        parsers = [
            self._parse_relative_day,
            self._parse_days_ago,
            self._parse_hours_ago,
            self._parse_week_month_year,
            self._parse_specific_date,
            self._parse_time_of_day,
        ]

        for parser in parsers:
            try:
                result = parser(time_str)
                if result:
                    logger.debug(f"时间解析: '{time_str}' → {result.isoformat()}")
                    return result
            except Exception as e:
                logger.debug(f"解析器 {parser.__name__} 失败: {e}")
                continue

        logger.debug(f"无法解析时间: '{time_str}'，使用当前时间")
        return self.reference_time

    def _parse_relative_day(self, time_str: str) -> datetime | None:
        """
        解析相对日期：今天、明天、昨天、前天、后天
        """
        relative_days = {
            "今天": 0,
            "今日": 0,
            "明天": 1,
            "明日": 1,
            "昨天": -1,
            "昨日": -1,
            "前天": -2,
            "前日": -2,
            "后天": 2,
            "后日": 2,
            "大前天": -3,
            "大后天": 3,
        }

        for keyword, days in relative_days.items():
            if keyword in time_str:
                result = self.reference_time + timedelta(days=days)
                # 保留原有时间，只改变日期
                return result.replace(hour=0, minute=0, second=0, microsecond=0)

        return None

    def _parse_days_ago(self, time_str: str) -> datetime | None:
        """
        解析 X天前/X天后、X周前/X周后、X个月前/X个月后
        """
        # 匹配：3天前、5天后、一天前
        pattern_day = r"([一二三四五六七八九十\d]+)天(前|后)"
        match = re.search(pattern_day, time_str)

        if match:
            num_str, direction = match.groups()
            num = self._chinese_num_to_int(num_str)

            if direction == "前":
                num = -num

            result = self.reference_time + timedelta(days=num)
            return result.replace(hour=0, minute=0, second=0, microsecond=0)

        # 匹配：2周前、3周后、一周前
        pattern_week = r"([一二三四五六七八九十\d]+)[个]?周(前|后)"
        match = re.search(pattern_week, time_str)

        if match:
            num_str, direction = match.groups()
            num = self._chinese_num_to_int(num_str)

            if direction == "前":
                num = -num

            result = self.reference_time + timedelta(weeks=num)
            return result.replace(hour=0, minute=0, second=0, microsecond=0)

        # 匹配：2个月前、3月后
        pattern_month = r"([一二三四五六七八九十\d]+)[个]?月(前|后)"
        match = re.search(pattern_month, time_str)

        if match:
            num_str, direction = match.groups()
            num = self._chinese_num_to_int(num_str)

            if direction == "前":
                num = -num

            # 简单处理：1个月 = 30天
            result = self.reference_time + timedelta(days=num * 30)
            return result.replace(hour=0, minute=0, second=0, microsecond=0)

        # 匹配：2年前、3年后
        pattern_year = r"([一二三四五六七八九十\d]+)[个]?年(前|后)"
        match = re.search(pattern_year, time_str)

        if match:
            num_str, direction = match.groups()
            num = self._chinese_num_to_int(num_str)

            if direction == "前":
                num = -num

            # 简单处理：1年 = 365天
            result = self.reference_time + timedelta(days=num * 365)
            return result.replace(hour=0, minute=0, second=0, microsecond=0)

        return None

    def _parse_hours_ago(self, time_str: str) -> datetime | None:
        """
        解析 X小时前/X小时后、X分钟前/X分钟后
        """
        # 小时
        pattern_hour = r"([一二三四五六七八九十\d]+)小?时(前|后)"
        match = re.search(pattern_hour, time_str)

        if match:
            num_str, direction = match.groups()
            num = self._chinese_num_to_int(num_str)

            if direction == "前":
                num = -num

            return self.reference_time + timedelta(hours=num)

        # 分钟
        pattern_minute = r"([一二三四五六七八九十\d]+)分钟(前|后)"
        match = re.search(pattern_minute, time_str)

        if match:
            num_str, direction = match.groups()
            num = self._chinese_num_to_int(num_str)

            if direction == "前":
                num = -num

            return self.reference_time + timedelta(minutes=num)

        return None

    def _parse_week_month_year(self, time_str: str) -> datetime | None:
        """
        解析：上周、上个月、去年、本周、本月、今年
        """
        now = self.reference_time

        if "上周" in time_str or "上星期" in time_str:
            return now - timedelta(days=7)

        if "上个月" in time_str or "上月" in time_str:
            # 简单处理：减30天
            return now - timedelta(days=30)

        if "去年" in time_str or "上年" in time_str:
            return now.replace(year=now.year - 1)

        if "本周" in time_str or "这周" in time_str:
            # 返回本周一
            return now - timedelta(days=now.weekday())

        if "本月" in time_str or "这个月" in time_str:
            return now.replace(day=1)

        if "今年" in time_str or "这年" in time_str:
            return now.replace(month=1, day=1)

        return None

    def _parse_specific_date(self, time_str: str) -> datetime | None:
        """
        解析具体日期：
        - 2025-11-05
        - 2025/11/05
        - 11月5日
        - 11-05
        """
        # ISO 格式：2025-11-05
        pattern_iso = r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"
        match = re.search(pattern_iso, time_str)
        if match:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)

        # 中文格式：11月5日、11月5号
        pattern_cn = r"(\d{1,2})月(\d{1,2})[日号]"
        match = re.search(pattern_cn, time_str)
        if match:
            month, day = map(int, match.groups())
            # 使用参考时间的年份
            year = self.reference_time.year
            return datetime(year, month, day)

        # 短格式：11-05（使用当前年份）
        pattern_short = r"(\d{1,2})[-/](\d{1,2})"
        match = re.search(pattern_short, time_str)
        if match:
            month, day = map(int, match.groups())
            year = self.reference_time.year
            return datetime(year, month, day)

        return None

    def _parse_time_of_day(self, time_str: str) -> datetime | None:
        """
        解析一天中的时间：
        - 早上、上午、中午、下午、晚上、深夜
        - 早上8点、下午3点
        - 8点、15点
        """
        now = self.reference_time
        result = now.replace(minute=0, second=0, microsecond=0)

        # 时间段映射
        time_periods = {
            "早上": 8,
            "早晨": 8,
            "上午": 10,
            "中午": 12,
            "下午": 15,
            "傍晚": 18,
            "晚上": 20,
            "深夜": 23,
            "凌晨": 2,
        }

        # 先检查是否有具体时间点：早上8点、下午3点
        for period in time_periods.keys():
            pattern = rf"{period}(\d{{1,2}})点?"
            match = re.search(pattern, time_str)
            if match:
                hour = int(match.group(1))
                # 下午时间需要+12
                if period in ["下午", "晚上"] and hour < 12:
                    hour += 12
                return result.replace(hour=hour)

        # 检查时间段关键词
        for period, hour in time_periods.items():
            if period in time_str:
                return result.replace(hour=hour)

        # 直接的时间点：8点、15点
        pattern = r"(\d{1,2})点"
        match = re.search(pattern, time_str)
        if match:
            hour = int(match.group(1))
            return result.replace(hour=hour)

        # HH:MM[:SS] 格式
        pattern_time = r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?"
        match = re.search(pattern_time, time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            second = int(match.group(3)) if match.group(3) else 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return result.replace(hour=hour, minute=minute, second=second)

        return None

    def _parse_combined_time(self, time_str: str) -> datetime | None:
        """
        解析组合时间表达：今天下午、昨天晚上、明天早上
        """
        # 先解析日期部分
        date_result = None

        # 相对日期关键词
        relative_days = {
            "今天": 0, "今日": 0,
            "明天": 1, "明日": 1,
            "昨天": -1, "昨日": -1,
            "前天": -2, "前日": -2,
            "后天": 2, "后日": 2,
            "大前天": -3, "大后天": 3,
        }

        for keyword, days in relative_days.items():
            if keyword in time_str:
                date_result = self.reference_time + timedelta(days=days)
                date_result = date_result.replace(hour=0, minute=0, second=0, microsecond=0)
                break

        if not date_result:
            return None

        # 再解析时间段部分
        time_periods = {
            "早上": 8, "早晨": 8,
            "上午": 10,
            "中午": 12,
            "下午": 15,
            "傍晚": 18,
            "晚上": 20,
            "深夜": 23,
            "凌晨": 2,
        }

        for period, hour in time_periods.items():
            if period in time_str:
                # 检查是否有具体时间点
                pattern = rf"{period}(\d{{1,2}})点?"
                match = re.search(pattern, time_str)
                if match:
                    hour = int(match.group(1))
                    # 下午时间需要+12
                    if period in ["下午", "晚上"] and hour < 12:
                        hour += 12
                return date_result.replace(hour=hour)

        # 如果没有时间段，返回日期（默认0点）
        return date_result

    def _chinese_num_to_int(self, num_str: str) -> int:
        """
        将中文数字转换为阿拉伯数字

        Args:
            num_str: 中文数字字符串（如："一"、"十"、"3"）

        Returns:
            整数
        """
        # 如果已经是数字，直接返回
        if num_str.isdigit():
            return int(num_str)

        # 中文数字映射
        chinese_nums = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
            "零": 0,
        }

        if num_str in chinese_nums:
            return chinese_nums[num_str]

        # 处理 "十X" 的情况（如"十五"=15）
        if num_str.startswith("十"):
            if len(num_str) == 1:
                return 10
            return 10 + chinese_nums.get(num_str[1], 0)

        # 处理 "X十" 的情况（如"三十"=30）
        if "十" in num_str:
            parts = num_str.split("十")
            tens = chinese_nums.get(parts[0], 1) * 10
            ones = chinese_nums.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
            return tens + ones

        # 默认返回1
        return 1

    def format_time(self, dt: datetime, format_type: str = "iso") -> str:
        """
        格式化时间

        Args:
            dt: datetime对象
            format_type: 格式类型 ("iso", "cn", "relative")

        Returns:
            格式化的时间字符串
        """
        if format_type == "iso":
            return dt.isoformat()

        elif format_type == "cn":
            return dt.strftime("%Y年%m月%d日 %H:%M:%S")

        elif format_type == "relative":
            # 相对时间表达
            diff = self.reference_time - dt
            days = diff.days

            if days == 0:
                hours = diff.seconds // 3600
                if hours == 0:
                    minutes = diff.seconds // 60
                    return f"{minutes}分钟前" if minutes > 0 else "刚刚"
                return f"{hours}小时前"
            elif days == 1:
                return "昨天"
            elif days == 2:
                return "前天"
            elif days < 7:
                return f"{days}天前"
            elif days < 30:
                weeks = days // 7
                return f"{weeks}周前"
            elif days < 365:
                months = days // 30
                return f"{months}个月前"
            else:
                years = days // 365
                return f"{years}年前"

        return str(dt)

    def parse_time_range(self, time_str: str) -> tuple[datetime | None, datetime | None]:
        """
        解析时间范围：最近一周、最近3天

        Args:
            time_str: 时间范围字符串

        Returns:
            (start_time, end_time)
        """
        pattern = r"最近(\d+)(天|周|月|年)"
        match = re.search(pattern, time_str)

        if match:
            num, unit = match.groups()
            num = int(num)

            unit_map = {"天": "days", "周": "weeks", "月": "days", "年": "days"}
            if unit == "周":
                num *= 7
            elif unit == "月":
                num *= 30
            elif unit == "年":
                num *= 365

            end_time = self.reference_time
            start_time = end_time - timedelta(**{unit_map[unit]: num})

            return (start_time, end_time)

        return (None, None)

#!/usr/bin/env python3
"""Bot项目的主入口点"""

if __name__ == "__main__":
    # 设置Python路径并执行bot.py
    import sys
    from pathlib import Path

    # 添加当前目录到Python路径
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))

    # 执行bot.py的代码
    bot_file = current_dir / "bot.py"
    with open(bot_file, encoding="utf-8") as f:
        exec(f.read())


# 这个文件是为了适配一键包使用的，在一键包项目之外没有用6666

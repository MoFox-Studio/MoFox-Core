<div align="center">

# 🌟 MoFox_Bot
**🚀 基于 MaiCore 0.10.0 snapshot.5进一步开发的 AI 智能体，插件功能更强大**

</div>

<p align="center">
  <a href="https://github.com/MoFox-Studio/MoFox_Bot/blob/master/LICENSE">
    <img src="https://img.shields.io/github/license/MoFox-Studio/MoFox_Bot" alt="License">
  </a>
  <a href="https://www.python.org/downloads/release/python-3110/">
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=edb641" alt="Python 3.11+">
  </a>
  <a href="https://github.com/microsoft/pyright">
    <img src="https://img.shields.io/badge/types-pyright-797952.svg?logo=python&logoColor=edb641" alt="Pyright">
  </a>
  <a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json" alt="Ruff">
  </a>
  <a href="https://deepwiki.com/MoFox-Studio/MoFox_Bot">
    <img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki">
  </a>
  <br />
  <a href="https://qm.qq.com/q/YwZTZl7BG8">
    <img src="https://img.shields.io/badge/墨狐狐的大学-169850076-violet?style=flat-square" alt="QQ Group">
  </a>
</p>

---

<div align="center">

## 📖 项目简介

**MoFox_Bot** 是一个基于 [MaiCore](https://github.com/MaiM-with-u/MaiBot) `0.10.0 snapshot.5` 的 fork 项目。我们保留了原项目几乎所有核心功能，并在此基础上进行了深度优化与功能扩展，致力于打造一个**更稳定、更智能、更具趣味性**的 AI 智能体。


> [IMPORTANT]
> **第三方项目声明**
>
> 本项目Fork后由 **MoFox Studio** 独立维护，为 **MaiBot 的第三方分支**，并非官方版本。所有更新与支持均由我们团队负责，后续的更新与 MaiBot 官方无直接关系。

> [WARNING]
> **迁移风险提示**
>
> 由于我们对数据库结构进行了重构与优化，从官方 MaiBot 直接迁移至 MoFox_Bot **可能导致数据不兼容**。请在迁移前**务必备份原始数据**，以避免信息丢失。

 > [!NOTE]
 > **分支策略说明**
 >
 > - `classical` 分支持续维护当前稳定版本（主要进行修复与小特性），建议生产使用。
 > - `dev` 分支为重构主线，变动较大且不保证可用性，仅供开发与测试。
 > - 切换至稳定分支（classical）：
 >
 > ```powershell
 > git fetch
 > git switch classical
 > ```
 >
 > - 参与重构请基于 `dev` 分支提交 PR。

</div>

---

<div align="center">

## ✨ 核心功能

</div>

<table>
<tr>
<td width="50%">
 
### 🔧 MaiBot 0.10.0 snapshot.5 原版功能
- 🔌 **强大插件系统** - 全面重构的插件架构，支持完整的管理 API 和权限控制
- 💭 **实时思维系统** - 模拟人类思考过程
- 📚 **表达学习功能** - 学习群友的说话风格和表达方式
- 😊 **情感表达系统** - 情绪系统和表情包系统
- 🧠 **持久记忆系统** - 基于图的长期记忆存储
- 🎭 **动态人格系统** - 自适应的性格特征和表达方式
- 📊 **数据分析** - 内置数据统计和分析功能，更好了解麦麦状态
 
</td>
<td width="50%">
 
### 🚀 拓展功能
 
- 🧠 **AFC 智能对话** - 基于亲和力流，实现兴趣感知和动态关系构建
- 🔄 **数据库切换** - 支持 SQLite 与 PostgreSQL 自由切换，采用 SQLAlchemy 2.0 重新构建
- 🛡️ **反注入集成** - 内置一整套回复前注入过滤系统，为人格保驾护航
- 🎥 **视频分析** - 支持多种视频识别模式，拓展原版视觉
- 📅 **日程系统** - 让MoFox规划每一天
- 🧠 **拓展记忆系统** - 支持瞬时记忆和长期记忆等多种记忆方式
- 🎪 **完善的 Event** - 支持动态事件注册和处理器订阅，并实现了聚合结果管理
- 🔍 **内嵌魔改插件** - 内置联网搜索等诸多功能，等你来探索
- 🔌 **MCP 协议支持** - 集成 Model Context Protocol，支持外部工具服务器连接（仅 Streamable HTTP）
- 🌟 **还有更多** - 请参阅详细修改 [commits](https://github.com/MoFox-Studio/MoFox_Bot/commits)
 
</td>
</tr>
</table>

---

<div align="center">

## 🔧 系统要求

### 💻 基础环境

| 项目         | 要求                                     |
| ------------ | ---------------------------------------- |
| 🖥️ 操作系统 | Windows 10/11、macOS 10.14+、Linux (Ubuntu 18.04+) |
| 🐍 Python 版本 | Python 3.11 或更高版本                   |
| 💾 内存       | 建议 ≥ 4GB 可用内存                      |
| 💿 存储空间   | 建议 ≥ 4GB 可用空间                      |

### 🛠️ 依赖服务

| 服务         | 描述                                       |
| ------------ | ------------------------------------------ |
| 🤖 QQ 协议端  | [NapCatQQ](https://github.com/NapNeko/NapCatQQ) 或其他兼容协议端 |
| 🗃️ 数据库     | SQLite（默认）或 PostgreSQL（可选）             |
| 🔧 管理工具   | Chat2DB（可选，用于数据库可视化管理）      |

---

<div align="center">

## 🏁 快速开始

### 📦 安装与部署

> [!NOTE]
> 详细安装与配置指南请参考官方文档：
> - **Windows 用户部署指南**：[https://mofox-studio.github.io/MoFox-Bot-Docs/docs/guides/deployment_guide.html](https://mofox-studio.github.io/MoFox-Bot-Docs/docs/guides/deployment_guide.html)
> - **`bot_config.toml` 完整教程**：[https://mofox-studio.github.io/MoFox-Bot-Docs/docs/guides/bot_config_guide.html](https://mofox-studio.github.io/MoFox-Bot-Docs/docs/guides/bot_config_guide.html)

</div>

<div align="center">

### ⚙️ 配置要点

1.  📝 **核心配置**：编辑 `config/bot_config.toml`，设置 LLM API Key、Bot 名称等基础参数。
2.  🤖 **协议端配置**：确保使用 [NapCatQQ](https://github.com/NapNeko/NapCatQQ) 或兼容协议端，建立稳定通信。
3.  🗃️ **数据库配置**：选择 SQLite（默认）或配置 PostgreSQL 数据库连接。
4.  🔌 **插件配置**：在 `config/plugins/` 目录中启用或配置所需插件。

</div>

---

<div align="center">

## 🙏 致谢

我们衷心感谢以下开源项目为本项目提供的坚实基础：

| 项目                                       | 描述                 | 贡献             |
| ------------------------------------------ | -------------------- | ---------------- |
| 🎯 [MaiM-with-u/MaiBot](https://github.com/Mai-with-u/MaiBot) | 原版 MaiBot 框架     | 提供核心架构与设计 |
| 🐱 [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) | 高性能 QQ 协议端     | 实现稳定通信       |
| 🌌 [internetsb/Maizone](https://github.com/internetsb/Maizone) | 魔改空间插件         | 功能借鉴与启发     |

如果可以的话，请为这些项目也点个 ⭐️ ！(尤其是MaiBot)

</div>

---

<div align="center">

## ⚠️ 重要提示

> [!CAUTION]
> **请务必阅读以下内容：**
>
> - 本项目使用前，请仔细阅读并同意 [**用户协议 (EULA.md)**](EULA.md)。
> - 本应用生成的内容由 AI 大模型提供，请谨慎甄别其准确性。
> - 请勿将 AI 生成内容用于任何违法、违规或不当用途。
> - 所有 AI 输出不代表 MoFox Studio 的立场或观点。

</div>

---

<div align="center">


## 📄 开源协议
 
本项目基于 **[GPL-3.0](LICENSE)** 协议开源。
 
[![GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg?style=for-the-badge&logo=gnu)](LICENSE)
 
```
                                   Copyright © 2025 MoFox Studio
                            Licensed under the GNU General Public License v3.0
```
 
</div>
 
---
 
<div align="center">
 
**🌟 如果这个项目对你有帮助，请给我们一个 Star！**
 
**💬 有任何问题或建议？欢迎提交 Issue 或 Pull Request！**

**💬 [点击加入 QQ 交流群](https://qm.qq.com/q/jfeu7Dq7VS)**

_Made with ❤️ by [MoFox Studio](https://github.com/MoFox-Studio)_

</div>

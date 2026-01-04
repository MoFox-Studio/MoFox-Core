# 拆分管理器测试报告（临时）

- 日期：2026-01-04
- 运行环境：Windows，本地 `.venv`，Python 3.11.9
- 命令：`python -m pytest -q src/person_info/manager/tests/test_service.py`
- 覆盖范围：
  - `get_person_id` 行为一致性（数字/字符串、带前缀平台截取后缀）。
  - `sync_user_info` 创建新记录（昵称/平台/用户ID/初始 person_name）。
  - `sync_user_info` 更新已存在记录的昵称。
- 结果：
  - 通过：3
  - 失败：0
  - 警告：1 个 SQLAlchemy 2.0 弃用警告（`declarative_base`），源自 `src/common/database/core/models.py`，不影响当前用例。
- 备注：
  - 测试使用内存假实现（Fake CRUD/Repository/NamingService），未触发真实数据库或 LLM 请求。
  - 现阶段仅验证拆分模块的基本行为，未覆盖缓存键兼容性、并发路径或真实依赖交互。

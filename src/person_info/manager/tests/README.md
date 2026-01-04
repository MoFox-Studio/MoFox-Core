# tests 说明

用于存放 person_info 拆分管理器的测试脚本（单元/集成）。

- 建议覆盖：CRUD 流程、取名流程（去重/异常）、缓存失效、并发创建（UNIQUE 竞争）。
- 暂未接入主流程，可先对 `PersonInfoService`、`PersonInfoRepository`、`PersonNamingService` 做隔离测试。

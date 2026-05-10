# 企业数据问答平台

这是一个面向 SQLite / MySQL 的企业数据问答系统。用户连接数据库后，系统会自动构建 schema 工作区，支持导入表字段注释、业务文档、Question-SQL 示例和错误修复记忆，并通过 Web 前端生成 SQL。

## 目录说明

- `api/`：FastAPI 后端接口
- `agent/`：Text-to-SQL 主流程
- `connectors/`：SQLite / MySQL 连接器
- `schema/`：schema profiling、自动注释、手写注释合并
- `schema_graph/`：schema graph 和图裁剪
- `memory/`：业务文档、Question-SQL、错误修复等持久化记忆
- `retrieval/`：A/B/C 示例召回
- `frontend/`：React Web 前端
- `data/workspaces/`：每个数据库的持久化工作区

## 注意

MySQL 密码不会保存到工作区。需要执行 SQL 时，请在前端输入本次会话密码后进入工作区。

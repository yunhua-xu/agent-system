# 项目二 说明

MCP 是 Model Context Protocol（模型上下文协议），让 Agent 调用外部工具。

## 目录
- `agent_graph.py`  项目二的 Agent 主程序（LangGraph 建图：agent 节点 + tools 节点 + 条件边）
- `tools.py`       八个工具的集中定义 + 全项目唯一的 `TOOLS` 清单 + `TOOL_MAP` 对照表（联网搜索 / 计算器 / 两数相加 / 查时间 / 查天气 / 读文件 / 查快递 / 记住事实）
- `tools5.py`      Day44 的工具强化版（联网搜索带降级链），早期文件
- `memory.py`      记忆模块（短期摘要 + 长期 ChromaDB）—— ★长期记忆 2026-10-08 已接进主链路并验证；短期摘要部分要有会话概念才能接（`api.py` 目前无状态）
- `ui.py` / `thought_chain.py`  Streamlit 网页 + 思考链整理逻辑

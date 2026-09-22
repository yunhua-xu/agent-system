# 项目二 说明

MCP 是 Model Context Protocol（模型上下文协议），让 Agent 调用外部工具。

## 目录
- `agent_graph.py`  项目二的 Agent 主程序（LangGraph 建图：agent 节点 + tools 节点 + 条件边）
- `tools.py`       五个工具的集中定义（联网搜索 / 计算器 / 查时间 / 查天气 / 读文件）
- `tools5.py`      Day44 的工具强化版（联网搜索带降级链），早期文件
- `memory.py`      记忆模块（短期摘要 + 长期 ChromaDB）—— 独立可跑，尚未接入主链路
- `ui.py` / `thought_chain.py`  Streamlit 网页 + 思考链整理逻辑

# -*- coding: utf-8 -*-
# mcp_client.py = MCP 客户端：去连上服务器（mcp_server.py / server.py），列工具、调工具
# 目标：把 MCP 上的工具"翻译"成 LangChain 能用的 tool，塞进我们的 Agent
# 【本机实测】必须用 cmd 运行，不能在 IDLE 里跑（IDLE 给不了真管道），详见文件末尾说明

import sys                                            # sys = system，用来拿当前 Python 解释器路径
import os                                             # os = 操作系统接口，用来读环境变量
import asyncio                                        # asyncio = 异步库，MCP 客户端必须跑在异步环境里
from pathlib import Path                              # Path = 路径的意思

# 把输出编码固定成 utf-8，免得 cmd 里中文变乱码（失败也不影响运行，所以用 try 包住）
try:                                                  # try = 试着做
    sys.stdout.reconfigure(encoding="utf-8")          # reconfigure = 重新设置编码
except Exception:                                     # 万一这个环境不支持就算了
    pass                                              # pass = 什么都不做，跳过

# ---------- 第 1 步：导入 MCP 客户端需要的包（没装就友好提示）----------
try:                                                          # 试着导入
    from mcp import ClientSession, StdioServerParameters      # ClientSession = 客户端会话；StdioServerParameters = 启动服务器子进程要的参数
    from mcp.client.stdio import stdio_client                 # stdio_client = 用"标准输入输出"方式连本地服务器
except ImportError:                                           # ImportError = 导入失败
    # SystemExit = 直接结束程序并打印下面这段话（不是崩溃，是"友好地拒绝运行"）
    raise SystemExit(
        "还没安装 MCP 客户端包，本文件跑不起来。请先在命令行运行：\n"
        "    pip install mcp\n"
        "装完再运行：python mcp_client.py"
    )

# ---------- 第 2 步：找到要连接的服务器脚本 ----------
# __file__ = 当前这个 mcp_client.py 文件本身；.resolve() = 转成绝对路径；.parent = 它所在的文件夹
_HERE = Path(__file__).resolve().parent

# 服务器脚本：优先找 server.py；如果没有，就退回 mcp_server.py（两种文件名都能跑，省得你改名）
SERVER_SCRIPT = _HERE / "server.py"                   # "/" 在这里是"拼路径"，不是除法
if not SERVER_SCRIPT.exists():                        # .exists() = 存在吗
    SERVER_SCRIPT = _HERE / "mcp_server.py"           # 退而求其次


# ---------- 第 3 步：定义"怎么启动服务器" ----------
def build_server_params() -> StdioServerParameters:   # -> 表示返回一个"启动参数对象"
    """构造启动服务器的参数：用当前这个 Python 解释器去跑它。"""
    return StdioServerParameters(                     # 一个"参数盒子"
        command=sys.executable,                       # sys.executable = 当前 python.exe 的完整路径（保证用同一个 Python）
        args=[str(SERVER_SCRIPT)],                    # args = arguments 参数，要跑哪个脚本
        env=None,                                     # env = environment 环境变量，None = 用默认的
    )


# ---------- 第 4 步：把 MCP 工具手动包成 LangChain 工具 ----------
# 类型对照表：MCP 声明的类型 -> Python 类型（dict = 字典，一行搞定映射）
TYPE_MAP = {"string": str, "integer": int, "number": float, "boolean": bool}


def get_input_schema(mcp_tool):
    """取"MCP 工具要什么参数"的那份说明书。
    ★本机大坑：mcp 2.x 里这个属性叫 input_schema（下划线写法），
      mcp 1.x 叫 inputSchema（驼峰写法）。两个都试一遍，谁都不出错。"""
    return getattr(mcp_tool, "input_schema", None) or getattr(mcp_tool, "inputSchema", None) or {}


def wrap_one_tool_as_langchain_tool(session, mcp_tool):   # session = 已连好的会话；mcp_tool = MCP 工具描述
    """手动把单个 MCP 工具包成 LangChain 工具。
    （理解原理用。本机只能走这条路，因为官方桥接包 langchain-mcp-adapters 尚不支持 mcp 2.x）"""
    from langchain_core.tools import StructuredTool   # StructuredTool = LangChain 里"带参数说明的工具"类
    from pydantic import create_model, Field          # create_model = 动态"造"一个参数模型；Field = 描述单个字段

    schema = get_input_schema(mcp_tool)               # 拿到入参说明书
    props = schema.get("properties", {})              # properties = 有哪些参数；.get(键, 默认值) 查不到就给默认
    required = set(schema.get("required", []))        # required = 哪些是必填；set() = 集合，用来快速判断"在不在里面"
    fields = {}                                       # fields = 准备交给 create_model 的字段表
    for pname, spec in props.items():                 # .items() = 把字典拆成一对对"键, 值"逐个拿出来
        ptype = TYPE_MAP.get(spec.get("type"), str)   # 查出 Python 类型，查不到就按字符串算
        default = ... if pname in required else None  # "..." 这个写法表示"必填"；否则默认 None
        fields[pname] = (ptype, Field(default, description=spec.get("description", "")))
    args_model = create_model(mcp_tool.name + "_Args", **fields)   # **fields = 把字典拆成一个个参数传进去

    async def _run(**kwargs):                         # async = 异步；**kwargs = 接收任意个"键=值"参数
        result = await session.call_tool(mcp_tool.name, kwargs)    # await = 等它跑完；把这次调用转发给 MCP 服务器
        return result.content[0].text                 # content[0].text 就是工具返回的那段文字

    return StructuredTool.from_function(              # from_function = "由一个函数造出一个工具"
        coroutine=_run,                               # coroutine = 传异步函数（★必须走异步，见第 7 步的坑）
        name=mcp_tool.name,                           # 沿用 MCP 服务器上的工具名
        description=mcp_tool.description or mcp_tool.name,   # 说明（模型靠它决定要不要用这个工具）
        args_schema=args_model,                       # args_schema = 参数模型（不传这个，模型就不知道要填 city）
    )


# ---------- 第 5 步：把 MCP 工具塞进 Agent（集成）----------
def build_agent(mcp_tools):                           # mcp_tools = 上面转出来的 LangChain 工具列表
    """造一个能调用 MCP 工具的 LangGraph Agent 并返回它。"""
    from dotenv import load_dotenv                    # 读 .env 文件里的 API key
    from langchain_openai import ChatOpenAI           # 用 OpenAI 兼容接口去连 DeepSeek
    from langgraph.graph import StateGraph, MessagesState, START   # MessagesState = 自动管理消息列表的状态
    from langgraph.prebuilt import ToolNode           # ToolNode = 专门负责"执行工具"的节点

    load_dotenv(r"E:/8月3日Ai学习计划/每日练习/agent_system/.env")   # r"..." = 原样字符串，反斜杠不当转义
    model = ChatOpenAI(                               # 造大模型对象（这里连的是 DeepSeek）
        model="deepseek-flash",                       # 模型名：官方支持 deepseek-flash / deepseek-v4-pro
        base_url="https://api.deepseek.com",          # base_url = DeepSeek 的接口地址
        api_key=os.getenv("DEEPSEEK_API_KEY"),        # 从环境变量拿 key（★别把 key 写死在代码里，更别传上网）
    )
    # ★关键：一定要 bind_tools，否则模型永远不会去调工具（tool_calls 永远是空列表）
    model_with_tools = model.bind_tools(mcp_tools)    # 把 MCP 工具"绑"到模型身上，让它知道有这些工具

    def call_model(state):                            # 节点1：让模型思考（要不要调工具、调哪个）
        return {"messages": [model_with_tools.invoke(state["messages"])]}

    def should_continue(state):                       # 判断函数：继续调工具，还是结束
        last = state["messages"][-1]                  # [-1] = 最后一条消息
        # getattr(msg, "tool_calls", None) = 取它的 tool_calls 属性，没有就返回 None；or [] 保证是列表
        return "tools" if getattr(last, "tool_calls", None) else "__end__"

    graph = StateGraph(MessagesState)                 # 造图
    graph.add_node("agent", call_model)               # 加"思考"节点
    graph.add_node("tools", ToolNode(mcp_tools))      # 加"执行工具"节点（MCP 工具也能直接放进去）
    graph.add_edge(START, "agent")                    # 起点 -> 思考
    graph.add_conditional_edges("agent", should_continue)   # 思考完 -> 交给判断函数决定走哪条路
    graph.add_edge("tools", "agent")                  # 执行完工具 -> 回去继续思考
    return graph.compile()                            # compile = 编译成真正可运行的图


# ---------- 第 6 步：主流程 ----------
async def main():                                     # async = 异步函数，内部才能 await
    """连服务器 -> 列工具 -> 转成 LangChain 工具 -> 塞进 Agent -> 问一句，看它调不调。"""
    print("要连接的服务器脚本：", SERVER_SCRIPT)       # 先把路径打出来，方便出错时对照
    params = build_server_params()                    # 拿到启动参数

    # stdio_client 会在后台帮我们启动服务器这个子进程，并架好"管道"
    async with stdio_client(params) as (read, write):        # async with = 异步版 with，用完自动断开
        async with ClientSession(read, write) as session:    # 建立会话
            await session.initialize()                       # initialize = 初始化握手（必须做，不做后面全报错）

            tools = (await session.list_tools()).tools       # list_tools = 让服务器报出它有哪些工具
            print("\n服务器上的工具 %d 个：" % len(tools))    # %d = 占位符，会被 len(tools) 替换成数字
            for t in tools:                                  # 逐个打印
                print("  -", t.name, "：", t.description)     # t.name = 工具名；t.description = 说明

            # ★所有 Agent 的活儿都必须在 async with 里面干！
            #   一旦出了这个 with，连接就断了，工具就调不动了。
            mcp_tools = [wrap_one_tool_as_langchain_tool(session, t) for t in tools]
            print("\n已转成 LangChain 工具：", [t.name for t in mcp_tools])

            app = build_agent(mcp_tools)                     # 造 Agent
            question = "北京天气怎么样？另外帮我在文档里搜一下 Agent 这个词。"
            print("\n提问：", question)

            # ★本机大坑：必须用 ainvoke（异步版），不能用 invoke（同步版）！
            #   MCP 工具是纯异步的，用同步的 invoke 会直接报
            #   NotImplementedError: StructuredTool does not support sync invocation.
            result = await app.ainvoke(                      # await = 等它跑完
                {"messages": [{"role": "user", "content": question}]},   # role="user" = 人类说的话
                config={"recursion_limit": 10},              # recursion_limit = 递归上限，控制这个循环最多跑几步
            )

            print("\n" + "=" * 62)
            print("消息轨迹（重点看第 2 条有没有 tool_calls）：")
            for i, m in enumerate(result["messages"], 1):    # enumerate(..., 1) = 序号从 1 开始，同时给序号和元素
                tc = getattr(m, "tool_calls", None) or []    # 取出这条消息里的工具调用记录
                print("  第%d条 %s  tool_calls=%s"
                      % (i, type(m).__name__, [x["name"] for x in tc]))   # type(m).__name__ = 类名
            print("=" * 62)
            print("最终回答：")
            print(result["messages"][-1].content)            # 最后一条消息的 content = 最终回答的正文


# ---------- 第 7 步：真正跑起来 ----------
if __name__ == "__main__":                            # 只有"直接运行本文件"时才执行（被 import 时不执行）
    asyncio.run(main())                               # asyncio.run = 启动异步主流程

# ============================================================
# 【本机实测】运行方式：必须在 cmd（或 PowerShell）里跑，不能在 IDLE 里跑！
#
#   cd /d "E:\8月3日Ai学习计划\每日练习\agent_system"
#   python mcp_client.py
#
# 在 IDLE 里跑会报 OSError（子进程创建失败），原因是 Windows 创建子进程
# 必须拿到 stderr 的真实文件句柄，而 IDLE 的 stdin/stdout/stderr 是假货，没有句柄。
# 这不是代码写错，是 IDLE 的先天限制。
#
# 【另】mcp_server.py 你不用自己跑 —— 它是被本文件自动拉起来的子进程。
# ============================================================

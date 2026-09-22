# api.py = 把我们的 Agent 包成一个"网络接口"的文件
# api = Application Programming Interface 的缩写，中文叫"应用程序接口"
#       说人话：别人（前端网页、别的程序）不用看我们的代码，只要按约定发一个网络请求过来，
#       我们就把答案发回去。
# 今天这个文件做 4 件事：
#   1) 定义请求/响应的数据格式（用 pydantic）
#   2) 提供 5 个"路由"（网址）：GET /、GET /health、POST /chat、POST /chat/stream、GET /history
#   3) 每来一次请求，就往 logs/trace.jsonl 追加一行日志（JSON Lines 格式）
#   4) 统计"这次到底调用了哪些工具"（必须遍历所有 message 累加，不能只看最后一条）

# ---------- 第 1 部分：导入需要的包 ----------
import os                                  # os = operating system（操作系统）的缩写，用来读环境变量、拼路径
import json                                # json 模块：用来把字典变成一行字符串（json.dumps），或反过来（json.loads）
import time                                # time 模块：用来算耗时（time.time() 取当前秒数）
from datetime import datetime              # datetime = 日期+时间的意思，用来打日志的时间戳
from pathlib import Path                   # Path = 路径的意思，比字符串拼路径更好用、不容易错
from typing import List, Dict, Any         # typing 里的 List/Dict/Any 是用来"标注类型"的，写清楚这个变量是什么类型

from fastapi import FastAPI, Query         # FastAPI = 网络框架；Query 用来声明网址问号后面的参数（如 ?limit=5）
from fastapi.responses import StreamingResponse, RedirectResponse   # StreamingResponse = 流式响应，一个字一个字往回发；RedirectResponse = 重定向响应，让浏览器自动跳到另一个网址
from pydantic import BaseModel             # BaseModel = 数据模型基类，用来定义"请求长什么样、响应长什么样"

from dotenv import load_dotenv             # load_dotenv = 加载 .env 文件的意思，把里面的 API key 读进环境变量
from langchain_openai import ChatOpenAI    # ChatOpenAI = 用来连大模型的聊天类（DeepSeek 兼容 OpenAI 的写法）
# 注：原来这里还有一句 from langchain_core.tools import tool（@tool 装饰器）。
#     ★Day53 改成从 tools.py 导入 TOOLS 之后，本文件不再自己定义工具，这句就用不上了，删掉。
from langchain_core.messages import HumanMessage, ToolMessage   # HumanMessage = "人说的话"（用户问题）；ToolMessage = "工具返回的结果"
from langgraph.prebuilt import create_react_agent  # create_react_agent = 直接帮我们搭好一个 ReAct 智能体的图

# ---------- 第 2 部分：一些固定配置 ----------
ENV_PATH = r"E:/8月3日Ai学习计划/每日练习/agent_system/.env"   # .env 文件的位置，里面存着 DEEPSEEK_API_KEY
# r"..." 前面的这个 r = raw（原始的）的意思，表示字符串里的 \ 不当转义符，Windows 路径常用它

LOG_DIR = Path(__file__).resolve().parent / "logs"   # __file__ = 本文件；.parent = 所在文件夹；再拼上 logs 子文件夹
LOG_FILE = LOG_DIR / "trace.jsonl"                   # trace = 追踪的意思；jsonl = 每行一个 JSON 的日志格式

# ---------- 第 3 部分：定义请求体和响应体的格式（pydantic） ----------
class ChatRequest(BaseModel):              # class = 定义类；ChatRequest = 聊天请求的意思，这里指"前端发过来的数据"
    question: str                          # question = 问题的意思；str 表示它必须是字符串。原计划写错成了 req.q，字段名对不上

class ChatResponse(BaseModel):             # ChatResponse = 聊天响应的意思，指"我们发回去的数据"
    answer: str                            # answer = 答案（字符串）
    tools_used: List[str]                  # tools_used = 用到的工具列表；List[str] 表示"字符串组成的列表"
    elapsed: float                         # elapsed = 已经过去的意思，这里指这次请求花了多少秒；float = 小数

# ---------- 第 4 部分：工具清单（★Day53 改：改成从 tools.py 统一取，不再自己另写一份）----------
# ★ 为什么非改不可？
#   原来这里是自己在文件里写了一个 get_time，然后 TOOLS = [get_time] —— 只有 1 个工具。
#   而 Day43 的 tools.py 里有 5 个：web_search / calculate / get_time / get_weather / read_file。
#   两条路（命令行那条走 agent_graph.py，网页这条走 api.py）用不同的工具箱，
#   结果就是：同一个 Agent，在命令行里会查天气，在网页接口上却说"我没有查天气的工具"。
#   ★ 本机实测过这个现象（问它"北京天气怎么样"，它答"我目前可用的工具只有 get_time"）。
#   所以改成 from tools import TOOLS，两条路共用同一份清单，谁也别想偷跑。
from tools import TOOLS                    # TOOLS = tools.py 里那张工具清单（5 个函数装成的 list）
# 注意：tools.py 里的函数本身就带 docstring 和类型标注，bind_tools / ToolNode 认这个，
#       不用再在外面包一层 @tool 装饰器。

# ---------- 第 5 部分：搭建 Agent（懒加载：第一次用的时候才搭） ----------
_agent = None                              # _agent 是模块级变量，先设成 None（空），表示"还没搭好"

def get_agent():                           # get_agent = 取得 Agent 的意思
    """第一次调用时创建 Agent，以后直接复用，避免每次请求都重新搭一遍。"""
    global _agent                          # global 表示下面要改的是"模块级的那个 _agent"，不是新建一个局部变量
    if _agent is None:                     # 如果还没搭过
        load_dotenv(ENV_PATH)              # 把 .env 里的 DEEPSEEK_API_KEY 读进环境变量
        model = ChatOpenAI(                # 创建一个"大模型对象"
            model="deepseek-flash",        # model = 用哪个模型，本机只能用 "deepseek-flash" 或 "deepseek-v4-pro"
            base_url="https://api.deepseek.com",        # base_url = 基础网址，DeepSeek 的接口地址
            api_key=os.getenv("DEEPSEEK_API_KEY"),      # api_key = 密钥，从环境变量里取，不写死在代码里
            temperature=0,                 # temperature = 温度，0 表示回答更稳定、不乱发挥
        )
        model_with_tools = model.bind_tools(TOOLS)   # bind_tools = 把工具"绑"给模型
        # 关键坑：不写这一句，模型的 tool_calls 永远是空的，图能跑但永远不会调用工具
        _agent = create_react_agent(model_with_tools, TOOLS)   # 用"绑了工具的模型 + 工具清单"搭出一个 ReAct 智能体
    return _agent                          # 返回搭好的 Agent

# ---------- 第 6 部分：从一堆 message 里提取答案、统计工具 ----------
def collect_tools(messages: list) -> List[str]:    # collect = 收集的意思；messages = 消息列表
    """遍历所有 message，累加每一次的 tool_calls，得出"这次调用了哪些工具"。"""
    names: List[str] = []                  # names = 工具名字的列表，先建一个空的
    for msg in messages:                   # 一条一条消息看过去
        calls = getattr(msg, "tool_calls", None) or []   # getattr = 取属性；取不到就得 None，再 or [] 兜底成空列表
        for call in calls:                 # 这条消息里的每个工具调用
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)  # 兼容字典/对象两种写法
            if name:                       # 名字不为空才算数
                names.append(name)         # 加进列表
    return names                           # 返回统计结果
    # 为什么要遍历所有消息？因为本机实测：最后那条 AIMessage 的 tool_calls 恒为 []，
    # 只看最后一条的话，永远统计不出调过工具！

def pick_answer(messages: list) -> str:    # pick = 挑选的意思
    """从后往前找，挑出真正给用户看的最终答案。"""
    for msg in reversed(messages):         # reversed = 反过来遍历，也就是从最后一条往前找
        content = getattr(msg, "content", "") or ""      # content = 消息内容
        if isinstance(content, list):      # 有些模型会把内容拆成列表（多段文字）
            content = "".join(              # join = 连接的意思，把列表里的文字拼成一整段
                part.get("text", "") if isinstance(part, dict) else str(part)  # 每段可能是字典也可能是字符串
                for part in content
            )
        if content and not (getattr(msg, "tool_calls", None) or []):   # 有内容、且这条不是"请求调用工具"的消息
            return content                 # 就是要它
    return ""                              # 都没找到就返回空字符串（原计划这里写的是 ... 空的，属于没写完）

# ---------- 第 7 部分：写日志（JSON Lines） ----------
def write_log(entry: Dict[str, Any]) -> None:   # entry = 一条日志记录（字典）；-> None 表示这个函数没有返回值
    """往 logs/trace.jsonl 追加一行 JSON。用 with open 自动开、自动关，不会漏关文件。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)   # mkdir = make directory 建文件夹；parents=True 表示上级目录也一起建；exist_ok=True 表示已存在也不报错
    line = json.dumps(entry, ensure_ascii=False)  # dumps = dump string 转成字符串；ensure_ascii=False 让中文原样保留不变成 \uXXXX
    with open(LOG_FILE, "a", encoding="utf-8") as f:   # "a" = append 追加模式，不会覆盖旧内容；encoding 指定编码
        f.write(line + "\n")               # 写一行，末尾加换行符。JSON Lines 就是"一行一个 JSON"
    # with 的好处：代码块结束时自动 f.close()，原计划漏了 open 和 close，这里一并解决

# ---------- 第 8 部分：真正跑 Agent 的两个函数（非流式 / 流式） ----------
def run_agent(question: str) -> Dict[str, Any]:   # run = 运行；返回一个字典
    """非流式：一次跑完，拿到完整答案。测试时这个函数会被替换成假的，避免花钱调 API。"""
    agent = get_agent()                    # 拿到 Agent
    result = agent.invoke({"messages": [HumanMessage(content=question)]})   # invoke = 调用；传进去一条"用户消息"
    # invoke 是同步调用：发出去 → 等它跑完 → 一次性拿回全部结果
    messages = result["messages"]          # 结果里有个 messages 键，是整轮对话的所有消息
    return {                               # 返回我们关心的两样东西
        "answer": pick_answer(messages),                 # 最终答案
        "tools_used": collect_tools(messages),           # 这轮用到的工具（遍历累加得出）
    }

def stream_agent(question: str):           # 生成器函数：用 yield 一段一段往外吐
    """流式：像打字机一样，大模型吐一个字我们发一个字。产出两种事件（字典）。"""
    # yield = 产出的意思。带 yield 的函数叫"生成器"，每 yield 一次就暂停一下，外面就能拿到一段
    agent = get_agent()                    # 拿到 Agent
    tools_used: List[str] = []             # 边流边统计用到哪些工具
    for chunk, meta in agent.stream(       # stream = 流式调用；stream_mode="messages" 表示"一个 token 一个 token 地吐"
        {"messages": [HumanMessage(content=question)]},
        stream_mode="messages",            # messages 模式的每一项是 (消息块, 附加信息) 这样的二元组
    ):
        if isinstance(chunk, ToolMessage):   # 实测坑：工具的执行结果也会被流出来，那是给模型看的中间产物，不该发给用户
            continue                         # continue = 跳过这一次循环，直接看下一条
        for call in (getattr(chunk, "tool_calls", None) or []):   # 这一小块里如果有工具调用
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name and name not in tools_used:                   # 没记录过才记
                tools_used.append(name)                           # 记下工具名字
        text = getattr(chunk, "content", "") or ""                # 这一小块的文字内容
        if isinstance(text, list):         # 内容可能是列表，先拼成字符串
            text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in text)
        if text:                           # 有文字才往外发
            yield {"type": "token", "text": text}                 # token = 一小片文字
    yield {"type": "tools", "names": tools_used}                  # 整轮结束时，报告用到了哪些工具

# ---------- 第 9 部分：创建 FastAPI 应用 ----------
app = FastAPI(title="Agent API", version="1.0")   # app = 应用对象，所有路由都挂在它上面

# ---------- 第 10 部分：定义 5 个路由（网址） ----------
@app.get("/")                              # @app.get = 用 GET 方式访问；"/" 是根网址（打了总机、没转分机）
def root():                                # root = 根的意思，自己起的函数名
    """访问根网址时自动跳到 /docs 测试页面，省得每次记网址（原来没这条，打 / 会 404）。"""
    return RedirectResponse(url="/docs")   # RedirectResponse = 重定向响应；url="/docs" = 跳到那个网址去

@app.get("/health")                        # @app.get = 这个方法用 GET 方式访问；GET 一般用来"读"数据
def health():                              # health = 健康检查的意思
    """健康检查：用来确认服务还活着。运维和 Docker 都用它探活。"""
    return {"status": "ok"}                # status = 状态；返回 {"status": "ok"} 就表示服务正常

@app.post("/chat")                         # @app.post = 用 POST 方式访问；POST 一般用来"提交"数据
def chat(req: ChatRequest):                # req = request（请求）的缩写，自己起的参数名；类型是上面定义的 ChatRequest
    """非流式聊天：一问一答，等 Agent 跑完再一次性返回。"""
    start = time.time()                    # 记下开始时刻（秒数）
    success = True                         # 先假设成功，出错了再改成 False
    try:                                   # try = 试着执行，出错会跳到 except
        result = run_agent(req.question)   # 调 Agent；req.question 就是请求里的 question 字段（不是 req.q）
        answer = result["answer"]          # 取出答案
        tools_used = result["tools_used"]  # 取出用到的工具
    except Exception as e:                 # except Exception as e = 抓到任何错误，错误对象叫 e
        success = False                    # 标记失败
        answer = f"出错啦：{e}"             # f"..." 是 f-string，能把变量塞进字符串里
        tools_used = []                    # 失败时工具列表为空
    elapsed = round(time.time() - start, 3)   # 耗时 = 现在 - 开始；round(..., 3) 表示保留 3 位小数
    write_log({                            # 追加一行日志（字段尽量全，方便以后统计）
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),   # 时间
        "question": req.question,          # 问题
        "tools_used": tools_used,          # 调用了哪些工具
        "elapsed": elapsed,                # 耗时（秒）
        "success": success,                # 成功还是失败
        "mode": "sync",                    # 这次是"非流式"还是"流式"
    })
    return ChatResponse(answer=answer, tools_used=tools_used, elapsed=elapsed)   # 按约定格式返回

@app.post("/chat/stream")                  # 流式聊天路由
def chat_stream(req: ChatRequest):         # 同样接收 ChatRequest
    """流式聊天：边生成边往回发，前端能实现"打字机效果"。"""
    def event_generator():                 # 里面这个小函数就是"生成器"，StreamingResponse 会一段段地读它
        # 注意：生成器里的代码，是在"响应已经开始发送之后"才真正执行的
        start = time.time()                # 记开始时间
        tools_used: List[str] = []         # 用到的工具
        full_text = ""                     # 把发出去的文字攒起来，方便最后写日志
        success = True                     # 先假设成功
        try:
            for event in stream_agent(req.question):    # 一段一段地拿事件
                if event["type"] == "token":            # 如果是"文字片"
                    full_text += event["text"]          # 攒起来
                    yield event["text"]                 # 立刻发出去
                elif event["type"] == "tools":          # 如果是"工具报告"
                    tools_used = event["names"]         # 记下来
        except Exception as e:                          # 出错也要告诉前端，而不是默默断掉
            success = False
            yield f"\n[出错] {e}"                        # 把错误当成文字发出去
        elapsed = round(time.time() - start, 3)         # 算耗时
        write_log({                                     # 流式请求同样要写日志
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "question": req.question,
            "tools_used": tools_used,                   # 注意：这里用的是 stream_agent 最后报告的结果
            "elapsed": elapsed,
            "success": success,
            "mode": "stream",
            "answer_length": len(full_text),            # 流式时把答案长度也记下来（内容太长不往日志里塞）
        })
    return StreamingResponse(event_generator(), media_type="text/plain; charset=utf-8")
    # media_type = 媒体类型，告诉浏览器"我发的是纯文本，用 utf-8 编码"

@app.get("/history")                       # 查看历史日志
def history(limit: int = Query(default=10, ge=1, le=100)):   # limit = 要几条，默认 10 条，最少 1 条最多 100 条
    """返回最近 N 条日志。ge=1 le=100 是 FastAPI 的参数校验。"""
    if not LOG_FILE.exists():              # 日志文件都还没有
        return {"count": 0, "items": []}   # count = 条数；直接返回空列表
    with open(LOG_FILE, "r", encoding="utf-8") as f:    # "r" = read 读取模式
        lines = [ln for ln in f if ln.strip()]          # strip() 去掉空白；把空行过滤掉
    recent = lines[-limit:]                # 切片：取最后 limit 行（[-10:] 表示倒数 10 条）
    items = []                             # 用来装解析好的日志
    for ln in recent:                      # 一行一行处理
        try:
            items.append(json.loads(ln))   # loads = load string，把 JSON 字符串变回字典
        except json.JSONDecodeError:       # 万一某行坏了
            continue                       # 跳过，不让整个接口崩掉
    return {"count": len(items), "items": items}   # 返回条数和内容

# -*- coding: utf-8 -*-
# server.py = MCP 服务器：把我们自己写的工具"暴露"出去，让别的程序（比如 Agent）能调用
# MCP = Model Context Protocol（模型上下文协议），说白了就是"工具的统一插座标准"

# ---------- 第 1 步：导入 FastMCP ----------
# 本机没装 mcp / fastmcp 包，所以这里写"兼容两种导入"，装哪一种都能用
try:                                                  # try = 试着做，失败了就进 except
    from fastmcp import FastMCP                       # 新版包名：pip install fastmcp
except ImportError:                                   # ImportError = 导入失败的意思
    try:                                              # 再试老写法
        from mcp.server.fastmcp import FastMCP        # 老版包名：pip install mcp
    except ImportError:                               # 两种都没有 = 没装包
        # SystemExit = 直接结束程序并打印下面这段话（不是崩溃，是"友好地拒绝运行"）
        raise SystemExit(
            "检测到还没安装 MCP 相关的包，本文件跑不起来。请先在命令行运行：\n"
            "    pip install fastmcp\n"
            "（如果想用老写法也可以：pip install mcp）\n"
            "装完再运行：python server.py"
        )

from pathlib import Path                             # Path = 路径的意思，比字符串拼路径更安全

# ---------- 第 2 步：准备数据 ----------
# WEATHER_DB = weather database 天气数据库（这里先用假的演示数据，真接要换成天气 API）
WEATHER_DB = {                                        # 一个字典：城市名 -> 天气描述
    "北京": "28度 多云",                               # 键 = 城市，值 = 天气
    "上海": "30度 小雨",
    "广州": "33度 晴",
    "深圳": "32度 阴",
    "杭州": "29度 多云",
}

# DOCS_DIR = documents directory 文档目录，只允许在这个文件夹里搜（防路径穿越的关键）
# __file__ = 当前这个 server.py 文件本身；.parent = 它所在的文件夹
DOCS_DIR = Path(__file__).resolve().parent / "docs"    # 即 server.py 同级的 docs 文件夹

# ---------- 第 3 步：创建 MCP 服务器对象 ----------
mcp = FastMCP("my-agent-tools")                       # 起个名字，客户端连上后能看到这个服务名


# ---------- 第 4 步：用 @mcp.tool() 把函数注册成"工具" ----------
# 注意：FastMCP 靠 docstring（函数第一行的三引号说明）告诉大模型"这工具是干嘛的"
# 所以每个工具函数里的三引号说明千万别删！
@mcp.tool()                                           # 装饰器：把下面这个函数登记成 MCP 工具
def get_weather(city: str) -> str:                    # city = 城市名；-> str 表示返回字符串
    """查询指定城市的天气。参数 city 是城市名，比如"北京"。"""  # docstring：给模型看的说明书
    return WEATHER_DB.get(city, "暂无该城市天气数据")   # .get(键, 默认值)：查不到就返回默认值


@mcp.tool()                                           # 第二个工具：搜文件
def search_file(keyword: str) -> str:                 # keyword = 关键词的意思
    """在本地 docs 目录的 .txt / .md 文件里搜索关键词，返回命中的文件名、行号和那一行内容。"""
    # ---- 4.1 先确认 docs 目录存在 ----
    if not DOCS_DIR.exists():                         # .exists() = 存在吗
        return f"目录不存在：{DOCS_DIR}，请先建一个 docs 文件夹并放几个 .txt/.md 文件"

    # ---- 4.2 记录结果 ----
    hits = []                                         # hits = 命中的意思，用来装每一行结果
    MAX_HITS = 20                                     # 最多返回 20 条，防止结果太长刷屏

    # ---- 4.3 遍历 docs 目录下所有文件（rglob = recursive glob 递归查找）----
    for file_path in DOCS_DIR.rglob("*"):             # "*" 表示所有名字
        if not file_path.is_file():                   # 不是文件（是文件夹）就跳过
            continue                                  # continue = 跳过这一轮，继续下一个
        if file_path.suffix.lower() not in (".txt", ".md"):  # suffix = 后缀名
            continue                                  # 只要 .txt 和 .md

        # ---- 4.4 防路径穿越：确认这个文件真的在 docs 里 ----
        # .resolve() = 把路径里的 .. 之类全部展开成真实绝对路径
        real_path = file_path.resolve()               # real_path = 真实路径
        base_dir = DOCS_DIR.resolve()                 # base_dir = 基准目录（不许跑出它）
        # is_relative_to = 判断"是不是在某个目录下面"；不在就跳过（防止搜到 C 盘别的地方）
        if not real_path.is_relative_to(base_dir):
            continue

        # ---- 4.5 逐行读，找关键词 ----
        try:                                          # 有的文件编码怪，读不动就跳过
            with open(real_path, "r", encoding="utf-8") as f:   # with = 用完自动关文件
                for line_no, line in enumerate(f, start=1):      # enumerate = 同时给出序号和内容
                    if keyword in line:                            # 这一行含关键词
                        # 拼成："文件名:行号: 那一行的内容"（strip 去掉行尾换行）
                        hits.append(f"{file_path.name}:{line_no}: {line.strip()}")
                        if len(hits) >= MAX_HITS:                  # 够 20 条就停
                            break
        except (UnicodeDecodeError, OSError):          # 读不了就跳过这个文件
            continue
        if len(hits) >= MAX_HITS:
            break

    # ---- 4.6 整理返回 ----
    if not hits:                                      # 一条都没找到
        return f"没有搜到包含「{keyword}」的内容"
    return "\n".join(hits)                            # join = 用换行把列表拼成一大段文字


# ---------- 第 5 步：启动服务 ----------
if __name__ == "__main__":                            # 只有"直接运行本文件"时才执行（被 import 时不执行）
    mcp.run()                                         # 默认用 stdio（标准输入输出）方式运行，等客户端来连

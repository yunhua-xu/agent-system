# -*- coding: utf-8 -*-
# 上面这行是告诉 Python：这个文件用 UTF-8 编码，里面的中文注释才不会乱码。
# 文件名：tools5.py  —— ★2026-09-27 订正：这里原来写的是「文件名：tools.py」，是错的，
#   连自己的文件名都写错了。这个文件是 Day44 的「工具强化版」（联网搜索带降级链：
#   ddgs 连不上就回头用 duckduckgo_search），后来被 tools.py 取代，保留下来当学习记录。
#   ★ 真正在用的工具在 tools.py；本文件没有被任何代码 import（README 里也标注了它是早期文件）。

import os          # os = operating system（操作系统），用它来处理文件路径、判断文件在不在。
import ast         # ast = abstract syntax tree（抽象语法树），用它来"安全地"解析数学算式，比直接用 eval 安全。
import operator    # operator = 运算符，提供 + - * / % 这几个运算，配合上面的 ast 做安全计算。
import json        # json = JavaScript Object Notation，一种通用的数据格式，用来把结果转成字符串返回。
import datetime    # datetime = date（日期）+ time（时间），Python 自带的日期时间库。
from langchain_core.tools import tool   # tool = 工具，langchain 提供的装饰器，加在函数头上就变成一个"工具"。


# ============================================================================
# 第一部分：搜索能力的"优雅降级"准备
# 降级 = 优雅地退而求其次。优先用真实联网搜索；装不上或者连不上网，
#        就自动换成我们事先写好的一份"假数据"(mock)，保证代码永远不崩。
# ============================================================================

# 定义几个"模块级变量"（写在外面的变量，整个文件都能用）。
# 开头的下划线 _ 是一种"内部约定"：表示这是我自己内部用的小东西，别人不用管。
_ddgs_class = None          # 用来存放找到的搜索类（DDGS 这个类）。
_ddgs_source = ""           # 用来记录是从哪个包找到的，方便打印给人看。


def _find_search_class():
    """
    这个函数干一件事：按顺序去"找"能用哪个搜索包。
    先试新包 ddgs，再试老包 duckduckgo_search，都没有就返回 None。
    函数名 _find_search_class = 查找搜索类（class = 类，程序员把"一整套功能"叫类）。
    """
    global _ddgs_class, _ddgs_source   # global = 全局的，声明下面要修改的是上面那两个"全局变量"。

    # 如果之前已经找过了，就直接返回，不用重复找（这叫"缓存"）。
    if _ddgs_class is not None:
        return _ddgs_class

    # 第一次 try：新包名 ddgs（2024 年之后 duckduckgo-search 改了名字叫 ddgs）。
    try:
        import ddgs                                # import = 导入，把别人写好的功能拿过来用。
        _ddgs_class = ddgs.DDGS                    # DDGS = DuckDuckGo Search 的缩写，是那个搜索类。
        _ddgs_source = "ddgs"                      # 记下：这次是用新包找到的。
        return _ddgs_class
    except Exception:
        # except = 例外/捕获，上面那句出错就走到这里，什么都不做，继续往下试第二个包。
        pass

    # 第二次 try：老包名 duckduckgo_search（已弃用，但有些老电脑上装的是它）。
    try:
        from duckduckgo_search import DDGS         # 老包里的类名字就叫 DDGS。
        _ddgs_class = DDGS                         # 同样存起来。
        _ddgs_source = "duckduckgo_search"         # 记下：这次是用老包找到的。
        return _ddgs_class
    except Exception:
        pass

    # 两个包都没找到，返回 None（None = 空、什么都没有）。
    return None


# 下面这份是"备用的假数据"，当真实搜索用不了的时候拿它顶上。
# mock = 模拟的、假的（读音"莫克"）。这份字典的 key 是关键词，value 是搜索结果列表。
_MOCK_RESULTS = {
    # 每个结果都是一个字典，有三个 key：title（标题）、body（摘要正文）、href（网址链接）。
    "python": [
        {"title": "Python 官方网站", "body": "Python 是一门简单易学的编程语言，官网提供下载和文档。", "href": "https://www.python.org"},
        {"title": "Python 教程 - 菜鸟教程", "body": "面向初学者的 Python 基础教程，包含语法、数据类型、函数等。", "href": "https://www.runoob.com/python3/python3-tutorial.html"},
    ],
    "langchain": [
        {"title": "LangChain 官方文档", "body": "LangChain 是构建大模型应用的开发框架，支持工具调用和记忆。", "href": "https://python.langchain.com"},
        {"title": "LangGraph 官方文档", "body": "LangGraph 用图的方式编排智能体，支持状态、节点和条件边。", "href": "https://langchain-ai.github.io/langgraph/"},
    ],
    "ai": [
        {"title": "人工智能 - 维基百科", "body": "人工智能是研究如何让机器模拟人类智能的学科。", "href": "https://zh.wikipedia.org/wiki/人工智能"},
    ],
}

# 当搜索的关键词在上面的假数据里完全找不到时，用这一条兜底，保证永远有东西返回。
_MOCK_FALLBACK = [
    {"title": "示例结果（离线模拟）", "body": "当前电脑连不上搜索服务，这是一条本地模拟的结果，仅用于演示流程。", "href": "https://example.com"},
]


def web_search(query: str, max_results: int = 3) -> str:
    """
    web_search = 网页搜索（web = 网页，search = 搜索）。
    输入一个关键词，返回几条搜索结果的文字。联网失败会自动退回本地模拟数据。

    query = 查询的意思，这里指"你要搜的关键词"，是我自己起的参数名。
    max_results = 最多返回几条（max = 最大，results = 结果）。
    """
    # 先试着去"找"搜索包。
    search_class = _find_search_class()

    # 如果找到了搜索包，就尝试真的联网搜一次。
    if search_class is not None:
        try:
            # DDGS() 是创建一个搜索对象；with 的写法是为了用完自动关掉它（省资源）。
            with search_class() as ddgs:
                # ddgs.text(搜索词, ...) = 搜网页文字。搜索词按"位置"传（放第一个），别写 keyword=（本机实测会报 TypeError）。
                raw = list(ddgs.text(query, max_results=max_results))
            # 如果真搜到了结果（列表不是空的），就把每条整理成"标题 + 摘要 + 链接"。
            if raw:
                lines = []                                # lines = 行（复数），准备一个空列表装文字。
                for r in raw:                             # r 是每条结果的字典。
                    # r.get("title", "") = 取 title 这个 key 的值；key 不存在就返回空字符串，防止报错。
                    title = r.get("title", "")            # title = 标题。
                    body = r.get("body", "")              # body = 正文/摘要。
                    href = r.get("href", "")              # href = hypertext reference，网址链接。
                    lines.append(f"{title}: {body} ({href})")   # append = 追加，把整理好的一行塞进列表。
                print(f"[web_search] 数据来源：真实联网（{_ddgs_source}）")   # 打印一行，说明这次用的是哪种。
                return "\n".join(lines)                   # join = 连接，用换行符把列表拼成一整段文字返回。
            else:
                # 搜了，但一条都没搜到，打印说明后继续往下走，去用假数据。
                print(f"[web_search] 真实搜索没返回结果（{_ddgs_source}），改用本地模拟数据")
        except Exception as e:
            # 联网过程中只要出任何错（超时、被墙、没网），都走这里。
            print(f"[web_search] 真实搜索失败：{type(e).__name__}，改用本地模拟数据")
    else:
        # 连搜索包都没装上，直接说明。
        print("[web_search] 未安装 ddgs / duckduckgo_search，使用本地模拟数据")

    # ==== 下面是降级分支：用本地假数据 ====
    q = query.lower()                                  # lower = 变小写，这样搜 "Python" 和 "python" 都能匹配上。
    hits = []                                          # hits = 命中的结果，先准备一个空列表。
    for key, items in _MOCK_RESULTS.items():           # items() 把字典的"键和值"一对一对取出来。
        if key in q:                                   # 如果某个关键词出现在用户搜的词里，就算命中。
            hits.extend(items)                         # extend = 扩展，把这一组结果全部加进 hits。
    if not hits:                                       # 一个都没命中，就用兜底那条。
        hits = _MOCK_FALLBACK
    hits = hits[:max_results]                          # 切片，只取前 max_results 条。

    lines = []                                         # 准备装输出文字。
    for r in hits:
        lines.append(f"{r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})")
    return "\n".join(lines)


_OPS = {                                            # _OPS = 我起的名字，_ 开头表示"只在文件内部用"。
    ast.Add: operator.add,                          # 允许加号：语法树里的 Add 对应 operator.add。
    ast.Sub: operator.sub,                          # 允许减号。
    ast.Mult: operator.mul,                         # 允许乘号。
    ast.Div: operator.truediv,                      # 允许除号（truediv = 真除法，1/2 得 0.5）。
    ast.Mod: operator.mod,                          # 允许取余 %（7 % 3 得 1）。
}
# ★ 为什么不用 eval？eval 会把用户输入当代码执行。
#   有人输入 __import__('os').system('删库') 就会被真的执行，这是严重安全漏洞。
#   面试官问"你的 Agent 工具安全吗"，答"我不用 eval，我自己走 AST 白名单"直接加分。


def _calc_node(node):                               # _calc_node = 我起的名；node = 节点，语法树上的一个小格子。
    """递归计算语法树（内部函数，下划线开头表示不对外用）。"""
    if isinstance(node, ast.Constant):              # Constant = 常量节点，就是写在算式里的一个具体数字。
        if isinstance(node.value, bool):            # True/False 在 Python 里也算数字，单独挡掉。
            raise ValueError("只支持数字和 + - * / % 这些运算符。")
        if not isinstance(node.value, (int, float)):  # int = 整数，float = 小数。
            raise ValueError("只支持数字和 + - * / % 这些运算符。")
        return node.value                           # 是个合法数字，直接返回。
    if isinstance(node, ast.BinOp):                 # BinOp = binary operation 二元运算，比如 a + b。
        op = _OPS.get(type(node.op))                # 查白名单：这个运算符允许吗。
        if op is None:                              # 不在白名单里（比如 ** 乘方、// 整除）。
            raise ValueError("只支持数字和 + - * / % 这些运算符。")
        return op(_calc_node(node.left), _calc_node(node.right))   # 先算左边、再算右边，最后套运算符。
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):   # UnaryOp = 一元运算。
        return -_calc_node(node.operand)            # USub = unary subtract，就是负号，比如 -5。
    raise ValueError("只支持数字和 + - * / % 这些运算符。")   # 其它一律拒绝。


def calculate(expression: str) -> str:
    """
    calculate = 计算（意思是"算一下"）。
    输入一个数学算式字符串，比如 "23 * 7 + 5"，返回算好的结果。

    expression = 表达式/算式，指用户写的那串数学式子。
    """
    try:
        # 先"安检"：只允许算式里出现数字、括号、空格和 +-*/% 这几个符号。
        allowed = set("0123456789+-*/().% ")        # set = 集合，用来做"字符合不合法"的快速判断。
        if not set(expression) <= allowed:          # <= 表示"是它的子集"，即有没有混进其它字符。
            return "算式里有不认识的字符，我只支持数字和 + - * / % ( ) 这些符号。"

        # ast.parse(..., mode="eval") 把算式解析成一棵树，非法算式会在这里直接抛错。
        tree = ast.parse(expression, mode="eval")
        # 再安检一次：只允许"算式"和"数字"两种节点，防止有人用 __import__ 之类的坏东西。
        for node in ast.walk(tree):                 # walk = 遍历整棵树的每个节点。
            if not isinstance(node, (ast.Expression, ast.Constant, ast.BinOp,
                                     ast.UnaryOp, ast.operator, ast.unaryop, ast.Load)):
                return "算式里出现了不允许的写法，我只支持最普通的四则运算。"

        # 自己走一遍语法树把它算出来 —— 全程不用 eval。
        # eval = evaluate（求值），它会把字符串当代码执行，是安全漏洞，生产环境一律禁用
        # （Day43 的 tools.py 里已经讲过为什么，面试官问"你的 Agent 工具安全吗"就答这一条）。
        result = _calc_node(tree.body)
        return f"{expression} = {result}"           # 返回像 "23 * 7 + 5 = 166" 这样的文字。
    except ZeroDivisionError:
        return "除数不能是 0。"                      # ZeroDivisionError = 除以零错误。
    except Exception as e:
        return f"算式没法计算：{type(e).__name__}"    # type(e).__name__ 是错误的名字，方便排查。


def get_time() -> str:
    """
    get_time = 获取时间（get = 得到，time = 时间）。
    不用输入任何东西，返回当前电脑的日期和时间。
    """
    now = datetime.datetime.now()                  # now = 现在，拿到当前这一刻的日期时间对象。
    # strftime = string format time（把时间格式化成字符串）。
    # %Y 四位年，%m 两位月，%d 两位日，%H 时，%M 分，%S 秒，%A 星期几的英文全称。
    return now.strftime("%Y-%m-%d %H:%M:%S %A")


# 下面这份是"假天气"数据表，key 是城市名，value 是天气描述。
_MOCK_WEATHER = {
    "北京": "晴，18~27 摄氏度，微风",
    "上海": "多云，20~26 摄氏度，东南风 3 级",
    "广州": "雷阵雨，25~31 摄氏度，南风 2 级",
    "深圳": "阴，26~30 摄氏度，风力较小",
    "杭州": "小雨，19~24 摄氏度，东北风 2 级",
}


def get_weather(city: str) -> str:
    """
    get_weather = 获取天气（weather = 天气）。
    输入城市名，返回天气情况。注意：这是本地模拟数据，不是真的联网查天气。

    city = 城市，指你要查的那座城市。
    """
    # _MOCK_WEATHER.get(city) 去表里查；查不到返回 None。
    info = _MOCK_WEATHER.get(city)
    if info is None:
        # 查不到就明确告诉对方，并把支持的城市列出来，别让它瞎猜。
        supported = "、".join(_MOCK_WEATHER.keys())   # keys() 取出所有城市名，再用顿号拼起来。
        return f"没有 {city} 的天气数据（这是本地模拟数据）。目前支持的城市：{supported}"
    return f"{city} 今天天气：{info}（本地模拟数据，非实时）"


def read_file(path: str, max_chars: int = 500) -> str:
    """
    read_file = 读文件（read = 读，file = 文件）。
    输入文件路径，返回文件开头的若干文字，最多 max_chars 个字符。

    path = 路径（文件在电脑上的位置）。
    max_chars = 最多读多少个字符（chars = characters 字符的缩写）。
    """
    # os.path.exists 判断这个路径在电脑上到底存不存在。
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    # os.path.isfile 判断这个路径是不是"文件"（因为也可能是文件夹）。
    if not os.path.isfile(path):
        return f"这是一个文件夹，不是文件：{path}"
    try:
        # open(..., "r", encoding="utf-8") = 以"只读"方式打开，用 UTF-8 编码读，中文才不乱码。
        # with 的写法是为了读完自动关闭文件。
        with open(path, "r", encoding="utf-8") as f:
            text = f.read(max_chars)               # read(max_chars) 只读前面这么多字符，防止文件太大卡死。
        # 如果文件比 max_chars 还长，就补一句提示，说明后面还有内容没读。
        note = ""
        if len(text) == max_chars:
            note = f"\n...（只显示了前 {max_chars} 个字符）"
        return f"文件 {path} 的内容：\n{text}{note}"
    except UnicodeDecodeError:
        # 说明这个文件不是纯文本（比如是图片、exe），UTF-8 读不出来。
        return f"这个文件不是能直接读的文本文件（编码不对）：{path}"
    except Exception as e:
        return f"读文件出错：{type(e).__name__}"


# ============================================================================
# 第二部分：把这 5 个函数"登记"成智能体能调用的工具
# 在函数头上加 @tool 装饰器，Python 就把它包装成工具对象，模型才能看见并调用它。
# 注意：@tool 靠函数下面的 """说明文字"""（叫 docstring，文档字符串）来判断这个工具是干嘛的，
#      所以每个工具函数的 docstring 一定要写清楚"什么时候该用它"，这里绝对不能省。
# ============================================================================

@tool
def web_search_tool(query: str, max_results: int = 3) -> str:
    """当需要上网查资料、了解最新信息、搜索不懂的概念时使用这个工具。输入搜索关键词。"""
    return web_search(query, max_results)     # 转手调用上面写好的真正实现，工具函数只负责"包装"。


@tool
def calculate_tool(expression: str) -> str:
    """当需要做数学计算（加减乘除、带括号的算式）时使用这个工具。输入一个算式，比如 23 * 7 + 5。"""
    return calculate(expression)


@tool
def get_time_tool() -> str:
    """当需要知道当前的日期和时间时使用这个工具。不需要输入任何参数。"""
    return get_time()


@tool
def get_weather_tool(city: str) -> str:
    """当需要查询某个城市的天气时使用这个工具。输入城市名，比如 北京。"""
    return get_weather(city)


@tool
def read_file_tool(path: str, max_chars: int = 500) -> str:
    """当需要查看电脑上某个文本文件的内容时使用这个工具。输入文件的完整路径。"""
    return read_file(path, max_chars)


# 把所有工具装进一个列表，方便后面一次性交给智能体（列表名叫 ALL_TOOLS，all = 全部）。
ALL_TOOLS = [
    web_search_tool,
    calculate_tool,
    get_time_tool,
    get_weather_tool,
    read_file_tool,
]


# ============================================================================
# 第三部分：__main__ 演示
# 直接运行 python tools.py 时会执行下面的代码；被别人 import 时不会执行。
# 这一段是给学员看的"亲眼验证"，证明 5 个工具都能用。
# ============================================================================

if __name__ == "__main__":     # __name__ 是 Python 自带的变量，直接运行时它的值就是 "__main__"。
    print("=" * 60)
    print("Day 44 演示：5 个工具的实际运行结果")
    print("=" * 60)

    # 先打印一下搜索工具现在走的是哪条路。
    cls = _find_search_class()
    print(f"搜索包探测结果：{'找到 -> ' + _ddgs_source if cls else '没找到（未安装 ddgs / duckduckgo_search）'}")
    print("-" * 60)

    print("[1/5] web_search_tool（联网搜索）")
    print(web_search_tool.invoke({"query": "python 教程", "max_results": 2}))   # invoke = 调用工具，参数用字典传。
    print("-" * 60)

    print("[2/5] calculate_tool（数学计算）")
    print(calculate_tool.invoke({"expression": "(12 + 8) * 3 - 100 / 4"}))
    print(calculate_tool.invoke({"expression": "1 / 0"}))                       # 故意算错，看看报错提示。
    print("-" * 60)

    print("[3/5] get_time_tool（当前时间）")
    print(get_time_tool.invoke({}))                                            # 没有参数，传空字典。
    print("-" * 60)

    print("[4/5] get_weather_tool（查天气）")
    print(get_weather_tool.invoke({"city": "北京"}))
    print(get_weather_tool.invoke({"city": "纽约"}))                             # 故意查一个没有的城市。
    print("-" * 60)

    print("[5/5] read_file_tool（读文件）")
    print(read_file_tool.invoke({"path": __file__, "max_chars": 120}))          # __file__ 就是这个文件自己的路径。
    print(read_file_tool.invoke({"path": "C:/这个文件不存在.txt"}))              # 故意读一个不存在的文件。
    print("-" * 60)

    print(f"一共登记了 {len(ALL_TOOLS)} 个工具：")
    for t in ALL_TOOLS:                                                        # t 是每个工具对象。
        print(f"  - {t.name}：{t.description.splitlines()[0]}")                 # name 是工具名，description 是那句 docstring。
    print("=" * 60)

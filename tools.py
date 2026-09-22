
# tools.py —— Agent 的"工具箱"：5 个工具 + 一张工具清单
# 放在 agent_system/ 目录下；Day45 的 agent_graph.py 会 from tools import TOOLS
#
# ★Day53 补上：原来是 3 个工具，现补成 5 个（加了"查天气"和"读文件"）。
#   为什么非补不可？因为 Day53 的边界测试（edge_cases.py）里 E11/E12 两条要【直接调用】
#   read_file 来测"读不存在的文件"和"路径穿越"，而原来的 tools.py 里根本没有这个函数 ——
#   edge_cases.py 第 142 行写的是 from tools import calculate, read_file, get_weather，
#   结果一 import 就 ImportError，整个 Day53 测试脚本一行都跑不起来。
#   这份改动和《Agent项目_代码勘误表_照着改》③ 里那份"已实测跑通"的 tools.py 是一致的。
import ast                          # ast = abstract syntax tree 语法树的缩写，固定叫法；安全计算靠它
import operator                     # operator = 运算符的意思，固定叫法；提供 + - * / 这四种运算
import os                           # os = operating system 操作系统，固定叫法；读文件那个工具要用它拼路径
from datetime import datetime       # datetime = 日期时间，固定叫法；从 datetime 模块里只取 datetime 这个类
import json                         # json = 把接口返回的那串文字解析成字典用的；固定叫法
import urllib.parse                 # urllib.parse = Python 自带的上网工具包；quote 把中文城市名转成网址能认的编码
import urllib.request               # urllib.request = Python 自带的发网络请求工具，不用额外 pip 装包


# ========== 工具 1：联网搜索（先用假数据占位）==========
def web_search(x: str) -> str:      # x = 参数名，自己起的变量名（三个工具故意都用 x，体现"签名统一"）
    """联网搜索最新信息。当用户问"最近/最新的某件事"时使用。参数 x 是搜索关键词。"""
    # ↑ 三引号这段叫 docstring（文档字符串，固定叫法）—— 不是给人看的，是给 AI 看的工具说明书
    #   本机实测：函数没有 docstring 就丢给 ToolNode 会直接报错
    #   ValueError: Function must have a docstring if description not provided.
    return (                                        # return = 返回，把结果交出去，固定叫法
        f"（当前是演示数据，未真的联网）搜索“{x}”的结果：\n"   # f"..." 叫 f-string，能在字符串里插变量
        "1. 这里以后放真实的搜索返回\n"                    # 真实实现以后接搜索 API 只改这几行
        "2. 本机实测：duckduckgo / startpage / brave / yahoo 全超时，只有 bing.com 通"
    )
    # 为什么先放假数据？因为今天的目标是"把流程跑通"。
    # 搜索接口不稳定会让整个 Agent 时好时坏，先用死数据把骨架搭起来，明天再换真的。


# ========== 工具 2：算数学（安全版，绝不用 eval）==========
_OPS = {                            # _OPS = 我起的名，下划线开头表示"只在文件内部用"；
    ast.Add: operator.add,          # 允许加号：语法树里的 Add 对应 operator.add
    ast.Sub: operator.sub,          # 允许减号
    ast.Mult: operator.mul,         # 允许乘号
    ast.Div: operator.truediv,      # 允许除号（truediv = 真除法，1/2 得 0.5）
}
# ★ 为什么不用 eval？eval 会把字符串当代码执行。
#   如果用户输入 __import__('os').system('rm -rf /')，eval 会真的去执行 —— 这是严重安全漏洞。
#   面试官问"你的 Agent 工具安全吗"，答"我不用 eval，我用 AST 白名单"直接加分。


def _calc(node) -> float:           # _calc = 我起的名；node = 节点，语法树上的一个小格子
    """递归计算语法树（内部函数，下划线开头表示不对外用）。"""
    if isinstance(node, ast.Constant):              # isinstance = 判断是不是某种类型，固定叫法
        if isinstance(node.value, bool):            # True/False 在 Python 里也算数字，单独挡掉
            raise ValueError("只支持 + - * / 和数字")  # raise = 主动报错，固定叫法
        if not isinstance(node.value, (int, float)):  # int = 整数，float = 小数
            raise ValueError("只支持 + - * / 和数字")
        return node.value                           # 是个合法数字，直接返回
    if isinstance(node, ast.BinOp):                 # BinOp = binary operation 二元运算，比如 a + b
        op = _OPS.get(type(node.op))                # 查白名单：这个运算符允许吗
        if op is None:                              # 不在白名单里（比如 ** 乘方、% 取余、// 整除）
            raise ValueError("只支持 + - * / 和数字")
        return op(_calc(node.left), _calc(node.right))   # 先算左边、再算右边，最后套运算符
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):   # UnaryOp = 一元运算
        return -_calc(node.operand)                 # USub = unary subtract，就是负号，比如 -5
    raise ValueError("只支持 + - * / 和数字")          # 其它一律拒绝（函数调用、属性访问全被挡）


def calculate(x: str) -> str:       # x = 参数名；收进来的是字符串，比如 "2+3*4"
    """计算数学表达式，只支持加(+)、减(-)、乘(*)、除(/)和数字。当用户要求算数时使用。参数 x 是表达式。"""
    if len(x) > 100:                                    # 太长的不算（防止有人塞一万层括号把程序撑爆）
        return "计算失败：表达式太长了（最多 100 个字符）"
    try:                                                # try = 试着做，固定叫法；出错就走 except
        tree = ast.parse(x, mode="eval")                # parse = 解析；mode="eval" 表示"只解析成表达式，不执行"
        return str(_calc(tree.body))                    # body = 语法树的主体；算完转成字符串返回
    except ZeroDivisionError:                           # ZeroDivisionError = 除以零错误，固定叫法
        return "计算失败：不能除以零"                        # 单独翻译成人话，比英文报错友好
    except Exception as e:                              # Exception = 异常，固定叫法；e = error 的缩写，我起的名
        return f"计算失败：{e}"                            # 工具失败必须返回一句人话，不能把异常抛给 Agent


# ========== 工具 3：查时间 ==========
def get_time(x: str = "") -> str:   # x 用不上，但必须留着 —— 为什么？见下面这段：
    """查询当前的日期和时间。当用户问"现在几点/今天几号"时使用。"""
    # ★ 原计划写的是 def get_time(): 不收参数，这是错的。
    #   ToolNode / 工具派发要求所有工具签名统一（都收一个字符串），
    #   否则模型传参进来时会 TypeError。所以写成 x: str = ""（= "" 表示默认空字符串，可以传也可以不传）。
    #   x 这个参数用不上，收到就丢掉，不影响功能。
    return datetime.now().strftime("%Y-%m-%d %H:%M")    # now() = 现在；strftime = 把时间格式化成字符串
    # %Y 四位年 / %m 两位月 / %d 两位日 / %H 24小时制时 / %M 分


# ========== 工具 4：查天气（★Day51 接上真实数据：open-meteo，免费、不用注册、不用密钥）==========
# ★ 原来是假的：return f"{city}：28度，多云" —— 不管问哪儿都返回同一句。
#   本机实测过：问"赣县"、问"南极"、甚至问一个空字符串，它都答"28度，多云"。
#   Day43 那行注释早就写着"以后接真实天气接口，只改这一行"，现在改的就是这一行。
# ★ 为什么挑 open-meteo？因为你 Day08 的 requests_demo.py 练的就是它（那串
#   api.open-meteo.com/v1/forecast?latitude=22.54&longitude=114.05 就是）。不给你引入新东西。
#   而且它免费、不用注册账号、不用密钥 —— 所以 .env 里不用再加任何东西。
# ★ 为什么要分两步？因为 open-meteo 只认经纬度，不认城市名：
#     第 1 步  城市名 → 经纬度   （geocoding-api.open-meteo.com）
#     第 2 步  经纬度 → 当前天气 （api.open-meteo.com）
# ★ 查不到就【明说查不到】，绝不编一个数字出来 —— 这也正是 Day53 边界用例要考的那一条。
UA = {"User-Agent": "Mozilla/5.0"}      # User-Agent = 用户代理，告诉服务器"我是谁"；有些接口不带头会被拒
WMO = {                                 # WMO = 世界气象组织。它把天气编成了数字，这张表是"数字 → 中文"的翻译表
    0: "晴", 1: "基本晴", 2: "多云", 3: "阴",                    # 0~3 是晴到阴
    45: "雾", 48: "雾凇",                                        # 45/48 是雾类
    51: "毛毛雨", 53: "小雨", 55: "中雨",                         # 5x 是毛毛雨类
    61: "小雨", 63: "中雨", 65: "大雨",                           # 6x 是雨类
    71: "小雪", 73: "中雪", 75: "大雪",                           # 7x 是雪类
    80: "阵雨", 81: "强阵雨", 82: "暴雨",                         # 8x 是阵雨类
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴伴冰雹",           # 9x 是雷暴类
}

def _get_json(url: str) -> dict:        # 名字前面加 _ 表示"只在本文件内部用"，外面别调它
    """发一个 GET 请求，把返回的 JSON 变成 Python 字典。"""
    req = urllib.request.Request(url, headers=UA)              # 把网址和请求头打包成一个"请求对象"
    with urllib.request.urlopen(req, timeout=15) as r:         # urlopen = 打开网址；timeout=15 = 最多等 15 秒
        return json.loads(r.read().decode("utf-8"))            # read 拿字节 → decode 解成文字 → loads 变成字典

def get_weather(city: str) -> str:      # city = 城市名，自己起的参数名；-> str 表示返回字符串
    """查询指定城市的实时天气。用户问"某地天气怎么样"时使用。参数 city 是城市名。"""
    try:                                # try = 试着执行；断网/超时/接口挂了就跳到 except，不会把整个 Agent 弄崩
        # ---- 第 1 步：城市名 → 经纬度 ----
        gurl = ("https://geocoding-api.open-meteo.com/v1/search?name="
                + urllib.parse.quote(city) + "&count=1&language=zh&format=json")
        # quote = 把中文城市名转成网址能认的编码（比如"北京"→%E5%8C%97%E4%BA%AC）
        g = _get_json(gurl)                                    # g = geocoding（地名查询）的返回
        hits = g.get("results") or []                          # results = 查到的地点列表；查不到就是空列表
        if not hits:                                           # 没查到这个地名
            return f"查不到「{city}」这个地名。换个更常见的名字，或者用它的上一级地名再试一次。"
        place = hits[0]                                        # 取最匹配的那一个
        lat, lon = place["latitude"], place["longitude"]        # lat = latitude 纬度；lon = longitude 经度
        # ---- 第 2 步：经纬度 → 当前天气 ----
        furl = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                "&current=temperature_2m,weather_code&timezone=auto" % (lat, lon))
        # temperature_2m = 地面以上 2 米处的温度（气象上就用这个高度）；timezone=auto = 按当地时区返回
        w = _get_json(furl)                                    # w = weather（天气）的返回
        cur = w.get("current") or {}                           # current = 当前天气那一块
        temp = cur.get("temperature_2m")                        # 温度
        code = cur.get("weather_code")                          # 天气代码（数字，要查 WMO 表翻译）
        if temp is None:                                       # 位置拿到了但没取到温度
            return f"定位到「{city}」了，但没取到温度，稍后再试。"
        desc = WMO.get(code, f"未知天气(代码{code})")             # 查表翻译；表里没有就照实说，不瞎编
        where = place.get("name") or city                      # 接口返回的标准地名
        return f"{where}：{temp}度，{desc}"                     # 跟原来一样的格式，只是数字换成真的了
    except Exception as e:                                     # 断网、超时、接口挂了都走这里
        return f"查天气失败（{type(e).__name__}），可能是网络不通或接口暂时不可用。"
        # ★ 这里【千万不能】return 一个编出来的温度 —— 宁可说"查不到"，也不能给假数据。


# ========== 工具 5：读文件（★只允许读本目录内的文件）==========
# BASE_DIR = 基准目录（base directory），就是这个文件 tools.py 自己所在的文件夹。
# ★为什么非要先算它？为了防"路径穿越"：
#   你只想让 Agent 读本目录的 a.txt，但如果有人传 ../../windows/win.ini，
#   就跳到目录外面、读到系统文件了。所以必须先拼出绝对路径、再检查有没有跑出界。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# __file__ = 本文件自己的路径（Python 内置变量，固定叫法）
# abspath = absolute path 绝对路径，把相对路径补全成从盘符开始的一条完整路径
# dirname = directory name 取所在文件夹


def read_file(path: str) -> str:    # path = 路径，自己起的参数名
    """读取本地文件内容。用户要求"打开/看一下某个文件"时使用。参数 path 是文件名。"""
    full = os.path.abspath(os.path.join(BASE_DIR, path))
    # join = 把两段路径拼起来（会自动补上 \ 分隔符）
    # 再套一层 abspath：这一步会把路径里的 .. 真正"算掉"，变成从盘符开始的一条实路径
    if not full.startswith(BASE_DIR):          # 拼完、算完，如果跑到本目录外面去了
        return "拒绝：只能读取本目录内的文件"    # 直接拒绝 —— 这就是"防路径穿越"那一句
    try:                                       # try = 试着读，出错就走 except
        with open(full, encoding="utf-8") as f:   # 打开文件；with 的写法是读完自动关
            return f.read()[:500]              # 只返回前 500 个字符（[：500] 是切片），防止文件太长撑爆上下文
    except Exception as e:                     # 文件不存在 / 编码不对，都会走这里
        return f"读取失败：{e}"                  # 工具失败必须返回一句人话，不能把异常抛给 Agent


# ========== 工具清单：必须用 list（列表），不能用 dict ==========
TOOLS = [web_search, calculate, get_time, get_weather, read_file]   # 五个函数装进一个列表；TOOLS = 我起的名
# ★ 为什么是 list 不是 dict？
#   后面 Day45 要写 model.bind_tools(TOOLS) 和 ToolNode(TOOLS)，
#   这两个函数本机实测都只吃 list。原计划里写 {"search": web_search, ...} 这种字典，传进去会报错。
#   注意：列表里装的是"函数本身"，不带括号 —— 带括号就成了"调用函数"，那是另一回事。


# ========== 自测：直接运行本文件才执行（被别人 import 时不执行）==========
if __name__ == "__main__":                  # __name__ = 内置变量，固定叫法；值是 "__main__" 说明是直接运行
    print("=== 逐个调用五个工具（看效果）===")
    print("1 搜索：", web_search("大模型 Agent 是什么"))
    print("2 计算：", calculate("2 + 3 * 4"))            # 正常算式
    print("3 计算：", calculate("(10 - 4) / 2"))          # 带括号的
    print("4 计算：", calculate("-5 + 2"))                # 带负号的
    print("5 计算：", calculate("1 / 0"))                 # 除以零，看报错长什么样
    print("6 危险：", calculate("__import__('os').system('echo 被攻击了')"))   # 危险输入，必须被挡
    print("7 时间：", get_time())                          # 不传参数，用默认值 ""
    print("8 时间：", get_time("x"))                       # 传一个没用的参数，看是否照样能跑
    print("9 天气：", get_weather("北京"))                  # Day51 接上真实数据：查天气（不再是假数据）
    print("10 文件：", read_file("tools.py"))              # Day53 新加的：读本目录里的文件，只给前 500 字
    print("11 穿越：", read_file("../../../windows/win.ini"))   # ★路径穿越，必须被拒绝
    print("12 没有：", read_file("这个文件肯定不存在_abc123.txt"))  # ★文件不存在，也必须返回一句人话
    print("=== 工具清单 ===")
    print("类型：", type(TOOLS).__name__)                  # 打印出来应该是 list
    print("工具名：", [t.__name__ for t in TOOLS])          # __name__ = 函数自己的名字
    # ↑ [t.__name__ for t in TOOLS] 叫"列表推导式"，意思是"把每个函数的名字取出来组成一个新列表"
    #   这个写法 Day45 会用到，今天先看一眼，不要求你会写。

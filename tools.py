
# tools.py —— Agent 的"工具箱"：8 个工具 + 【全项目唯一的一张工具清单】
# 放在 agent_system/ 目录下；Day45 的 agent_graph.py 会 from tools import TOOLS
# ★2026-10-07 合并：原来是"5 个工具 + 一张只有 5 个的清单"，而 agent_graph.py 里
#   还自己藏着另一张 6 个的清单，两张不一样。现在合并成这一张，7 个，两条路共用。
# ★2026-10-08 接记忆模块：加了第 8 个工具 remember_fact（让 Agent 自己决定"这句话值不值得记"）。
#   从这一天起是 8 个。上面那句"7 个"是 10-07 合并当天的数字，留着当历史记录，不是笔误。
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
import re                           # re = regular expression 正则表达式，固定叫法；从网页源码里"抠"标题和链接靠它
import html as _html                # html = Python 自带的网页实体处理模块；_html 是我起的别名，免得和函数名撞车


# ========== 工具 1：联网搜索（★2026-10-07 接上真实联网：360搜索 so.com）==========
# ★ 原来是假的：不管搜什么，都返回同一句"（当前是演示数据，未真的联网）"。
#   为什么换成 360 搜索？本机实测（2026-10-07），四个候选挨个试出来的：
#     · duckduckgo / google / brave —— ❌ 全部连接超时，国内网络根本到不了
#     · 百度 www.baidu.com —— ❌ 只回 1488 字节的反爬页面，解析不出任何结果
#     · 必应 cn.bing.com —— ⚠️ 通了，但中文相关度很差：搜"国产大模型 最新进展"，
#                              返回的前 10 条全是"精品国产专区""国产视频"这类垃圾站
#     · 360搜索 www.so.com —— ✅ 通了，相关度高，标题/摘要/真实网址都能正确抠出来
#   所以选它：国内可达、不用注册、不用密钥，当天就能跑通、能当场演示。
# ★ 为什么不注册一个搜索 API？—— 那样得等审核、等 key，面试前时间不够。
#   真要升级，只改 _search_360 这一个内部函数（换成博查 api.bochaai.com，需要 key），
#   上面的 web_search 一行都不用动 —— 这就是把"取数"和"包装"分开写的好处。

_SEARCH_UA = {                      # _ 开头 = 只在本文件内部用；这张表告诉服务器"我是浏览器"，伪装不好会被拒
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",            # Accept-Language = 接受的语言；告诉服务器优先给中文页面
    "Accept": "text/html,application/xhtml+xml",     # Accept = 接受的内容类型；要网页，不要图片
}


def _fetch_html(url: str, timeout: int = 12) -> str:
    """内部函数：发 GET 请求把网页源码拿回来，并自动试几种编码（中文站常见 utf-8 / gbk）。"""
    req = urllib.request.Request(url, headers=_SEARCH_UA)    # 把网址 + 请求头打包成一个"请求对象"
    with urllib.request.urlopen(req, timeout=timeout) as r:  # urlopen = 打开网址；timeout = 最多等多少秒
        raw = r.read()                                       # read() 拿到的是字节(bytes)，还不是文字
    for enc in ("utf-8", "gbk", "gb18030"):                  # 依次试着用这三种编码去解
        try:
            return raw.decode(enc)                           # 解成功就返回
        except UnicodeDecodeError:                           # UnicodeDecodeError = 解码错误，固定叫法；解不了就换下一种
            continue                                         # continue = 跳过本轮，接着循环试下一种
    return raw.decode("utf-8", "ignore")                     # 三种都不行就硬解 + 忽略错字（总比整个崩掉强）


def _clean_text(s: str) -> str:
    """内部函数：把一段 HTML 洗成干净的一行中文（去标签、还原 &amp; 这类暗号、压缩空格）。"""
    s = re.sub(r"<[^>]+>", "", s)          # 正则去掉所有 <...> 标签（标题里带 <em> 高亮，也得去掉）
    s = _html.unescape(s)                  # 把 &nbsp; &#0183; &amp; 这类"网页暗号"还原成正常字符
    return re.sub(r"\s+", " ", s).strip()  # \s+ = 一个或多个空白，全压成一个空格；strip = 去掉首尾空白


def _search_360(q: str, limit: int = 5, timeout: int = 12) -> list:
    """内部函数：抓 360 搜索结果，返回 [{"title":标题, "url":真实网址, "abstract":摘要}, ...]。"""
    page = _fetch_html("https://www.so.com/s?q=" + urllib.parse.quote(q), timeout)
    # quote = 把中文关键词转成网址能认的编码（"大模型" → %E5%A4%A7%E6%A8%A1%E5%9E%8B）
    out, seen = [], set()                # out = 结果列表；seen = 见过的网址集合，用来去重
    # ---- A 段：页面顶上那块"AI 新闻聚合卡"，结构跟普通结果不一样，得单独抠 ----
    pat_a = re.compile(                  # compile = 编译；把正则先编译好，后面反复用更快
        r'<a[^>]*data-mdurl="([^"]+)"[^>]*class="mh-news-title[^"]*"[^>]*>(.*?)</a>'
        r'\s*<p class="mh-news-desc[^"]*">(.*?)</p>', re.S)   # re.S = 让点号 . 也能匹配换行
    # ★ data-mdurl 是 360 埋在标签里的【真实网址】，不是它自己的跳转链接 —— 有它就不用再点一次还原了
    for url, title, desc in pat_a.findall(page):     # findall = 找出全部匹配，一次给一组
        if url not in seen:                          # 没见过的才收
            seen.add(url)                            # 记下来，防止后面重复收
            out.append({"title": _clean_text(title), "url": url, "abstract": _clean_text(desc)})
    # ---- B 段：普通搜索结果，一条长这样 ----
    #   <h3 class="res-title"><a data-mdurl="真网址">标题</a></h3> …… <p class="res-desc">摘要</p>
    pat_b = re.compile(
        r'<h3 class="res-title[^"]*"[^>]*>\s*<a[^>]*data-mdurl="([^"]+)"[^>]*>(.*?)</a>\s*</h3>'
        r'(.*?)(?=<li class="res-list|</ol>|$)', re.S)   # 括号里那串是"往前看"：抠到下一条结果为止
    for url, title, rest in pat_b.findall(page):     # rest = 这一条标题后面、到下一条结果之间的全部内容
        if url in seen:                              # A 段已经收过就跳过
            continue
        m = re.search(r'<p class="res-desc[^"]*">(.*?)</p>', rest, re.S)   # 在这段里找摘要
        seen.add(url)
        out.append({"title": _clean_text(title), "url": url,
                    "abstract": _clean_text(m.group(1)) if m else ""})    # 找不到摘要就留空，不编
    return out[:limit]                               # 切片，只要前 limit 条


def _resolve_sogou_link(href: str, timeout: int = 8) -> str:
    """内部函数：搜狗的结果链接是它自己的中转跳转，这个函数把真实网址问出来。
    原理：那个中转页只有 226 字节，里面就一句 window.location.replace("真网址")，抠出来即可。"""
    full = href if href.startswith("http") else "https://www.sogou.com" + href   # 补全成完整网址
    try:
        txt = _fetch_html(full, timeout)             # 抓那个 226 字节的中转页
    except Exception:
        return ""                                    # 还原失败就给空串，绝不让它把整个搜索拖崩
    m = re.search(r'location\.replace\("([^"]+)"\)', txt)   # 从 JS 里抠真网址
    if not m:                                        # 万一它换了写法
        m = re.search(r"URL='([^']+)'", txt)          # 试试 <meta http-equiv="refresh"> 那种
    return m.group(1) if m else ""                    # 抠到就返回，抠不到给空串


def _search_sogou(q: str, limit: int = 5, timeout: int = 12) -> list:
    """内部函数：抓搜狗（www.sogou.com）的结果，格式跟 _search_360 对齐。
    为什么还要第二个源？本机实测 360 对"Python 怎么读取 CSV 文件"这种编程问题返回 0 条
    （整页几乎全是它自家的 AI 卡片），同一条搜狗却能返回 6 条真结果 —— 两个源互补，一个不够用。"""
    page = _fetch_html("https://www.sogou.com/web?query=" + urllib.parse.quote(q), timeout)
    blocks = re.findall(                             # 搜狗把每条结果装在 <div class="vrwrap"> 里
        r'<div class="vrwrap".*?(?=<div class="vrwrap"|<div id="pagebar_container"|</body>)',
        page, re.S)                                  # 括号里是"往前看"：抠到下一条结果为止
    out = []
    for b in blocks:                                 # 逐块抠
        m = re.search(r'<h3 class="vr-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:                                    # 这块没有标题 —— 是广告或别的挂件，跳过
            continue
        title = _clean_text(m.group(2))              # 标题
        if not title:                                # 标题抠出来是空的，也跳过
            continue
        fav = re.search(r'zuowei_dir/([^"/]+?)\.ico', b)   # 搜狗把小图标的网址里塞了来源域名
        site = fav.group(1).replace("_", ".") if fav else ""   # www_runoob_com → www.runoob.com
        ab = re.search(r'<div class="fz-mid[^"]*"[^>]*>(.*?)</div>', b, re.S)   # 摘要
        out.append({"title": title, "href": m.group(1), "site": site,
                    "abstract": _clean_text(ab.group(1)) if ab else "", "url": ""})
        if len(out) >= limit:                        # 够数了就停，别白跑
            break
    for r in out:                                    # 把跳转链接逐条换成真实网址
        u = _resolve_sogou_link(r["href"], timeout)
        r["url"] = "" if "sogou.com" in u else u     # 没还原出来（还是搜狗自己地址）就当没有，
        # ↑ 这一句是必须的：搜狗有些结果的"链接"其实是它自己的站内再搜一次，
        #   直接给模型等于给了一条假网址。宁可不给网址，只给来源域名。
    return out


def web_search(x: str) -> str:      # x = 参数名，自己起的变量名（几个工具故意都用 x，体现"签名统一"）
    """联网搜索最新信息。当用户问"最近/最新的某件事"时使用。参数 x 是搜索关键词。"""
    # ↑ 三引号这段叫 docstring（文档字符串，固定叫法）—— 不是给人看的，是给 AI 看的工具说明书
    #   本机实测：函数没有 docstring 就丢给 ToolNode 会直接报错
    #   ValueError: Function must have a docstring if description not provided.
    # ★ 为什么用两个源？单靠一个都不够（本机实测，2026-10-07）：
    #   360搜索：中文新闻类问得准（"国产大模型 最新进展"给 5 条），但编程类会 0 条。
    #   搜狗　　：编程类问得好（"Python 怎么读取 CSV 文件"给 6 条），正好补 360 的空。
    #   所以策略是：先用 360，要是它给得太少（不到 3 条）再用搜狗补一手，两个拼起来。
    rows, used, errs = [], [], []                    # rows = 汇总结果；used = 哪几个源出了力；errs = 出错记录
    try:                                             # try = 试着做，固定叫法；断网/超时/页面改版都走 except
        rows = _search_360(x, limit=5)               # 主力：360 搜索
        if rows:                                     # 有货就记一笔
            used.append("360搜索")
    except Exception as e:                           # Exception = 异常，固定叫法；e = error 的缩写，我起的名
        errs.append(f"360搜索（{type(e).__name__}）") # 记下出错类型，最后好一起汇报；但不致命，还能走搜狗
    if len(rows) < 3:                                # 360 给得太少（本机实测：编程类问题会 0 条）
        try:
            extra = _search_sogou(x, limit=5)        # 再用搜狗补一手
            have = {r["title"] for r in rows}        # 已有的标题集合，用来去重
            for r in extra:                          # 逐条看
                if r["title"] not in have and len(rows) < 6:   # 没重复、且总数还没到 6
                    rows.append(r)                   # 收进来
            if extra:                                # 搜狗只要回了东西就记一笔
                used.append("搜狗")
        except Exception as e:                       # 搜狗也挂了
            errs.append(f"搜狗（{type(e).__name__}）")  # 记下来，但也不致命
    if not rows:                                     # 两个源都没捞到东西
        why = ("、".join(errs) + " 都失败了") if errs else "两个源都没有返回结果"
        return (f"联网搜索「{x}」失败：{why}。"
                "请如实告诉用户“联网搜索暂时不可用”，不要编造内容。")
        # ★ 这里【千万不能】编几条假结果返回 —— 宁可说"搜不到"，也不能给假数据。
    for r in rows:                                   # 补上"来源域名"（360 那边只有网址，没有单独的域名）
        if not r.get("site") and r.get("url"):
            r["site"] = urllib.parse.urlparse(r["url"]).netloc   # netloc = 网址里的域名部分
    lines = [f"以下是联网搜索「{x}」的真实结果（来源：{'、'.join(used)}）："]   # 表头；f"..." 叫 f-string
    for i, r in enumerate(rows, 1):                  # enumerate = 编号；从 1 开始给每条结果编号
        lines.append(f"{i}. {r['title']}")            # 标题
        if r.get("abstract"):                        # 摘要可能抠不到，空着就不占一行
            lines.append(f"   {r['abstract']}")       # 摘要
        tail = []                                    # tail = 这一条最后那行要拼的东西，有啥写啥
        if r.get("site"):                            # 来源域名
            tail.append(f"来源：{r['site']}")
        if r.get("url"):                             # 真实网址 —— 面试演示时能当场点开验证，这是关键
            tail.append(f"网址：{r['url']}")
        if tail:
            lines.append("   " + "  ".join(tail))
    lines.append("请基于以上真实结果回答，并说明信息来自哪个网址。")    # 收尾指令：给模型压一句，减少幻觉
    return "\n".join(lines)                          # join = 把列表里的行用换行符连成一整段文字返回


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


# ========== 工具 3：两数相加（★2026-10-07 从 agent_graph.py 搬过来的）==========
# ★它原来为什么在 agent_graph.py 里，不在这儿？—— 因为 Day45 写那个文件时顺手另起了一份工具，
#   从此两条路（网页 8501 / 接口 8000）的工具清单就对不上了。详见文件末尾"工具清单"那段。
#   2026-10-07 合并：全项目只留 tools.py 这一张清单，所以把它搬回工具箱。
def add(a: int, b: int) -> int:     # a、b = 两个加数，自己起的参数名；-> int 表示返回整数
    """计算两个整数相加。当用户问加法算数时使用这个工具。
    参数 a 是第一个加数，参数 b 是第二个加数。
    """
    # a: int, b: int = 这两个参数必须是整数，模型会按这个要求传参
    return a + b                    # 返回 a 加 b 的结果


# ========== 工具 4：查时间 ==========
def get_time(x: str = "") -> str:   # x 用不上，但必须留着 —— 为什么？见下面这段：
    """查询当前的日期和时间。当用户问"现在几点/今天几号"时使用。"""
    # ★ 原计划写的是 def get_time(): 不收参数，这是错的。
    #   ToolNode / 工具派发要求所有工具签名统一（都收一个字符串），
    #   否则模型传参进来时会 TypeError。所以写成 x: str = ""（= "" 表示默认空字符串，可以传也可以不传）。
    #   x 这个参数用不上，收到就丢掉，不影响功能。
    return datetime.now().strftime("%Y-%m-%d %H:%M")    # now() = 现在；strftime = 把时间格式化成字符串
    # %Y 四位年 / %m 两位月 / %d 两位日 / %H 24小时制时 / %M 分


# ========== 工具 5：查天气（★Day51 接上真实数据：open-meteo，免费、不用注册、不用密钥）==========
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


# ========== 工具 6：读文件（★只允许读本目录内的文件）==========
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


# ========== 工具 7：查快递（★会故意失败一次的"网络工具"）==========
# ★为什么故意让它失败？Day46 用它测「需要重试」这条场景：
#   第一次调用必定返回"网络超时"，模型要是会重试，第二次就能拿到结果；
#   不会重试的话就一直卡在失败上 —— 这样"到底会不会重试"才测得出来。
# ★2026-10-07 合并：这个工具连同它下面的计数器，都是从 agent_graph.py 搬过来的。
#   为什么搬？因为"快递工具被查了几次"本来就该归"快递工具"自己管，
#   而不是寄居在"搭图"那个文件里 —— 那个文件负责画图，不该负责记快递被查了几次。
_flaky_state = {"n": 0}    # flaky = 时好时坏的、不稳定的，固定叫法；这里记它被调了几次
# _ 开头 = 只在本文件内部用，外面别碰它


def reset_flaky():         # ★test_scenarios.py 每道题开跑前要调它一下：把计数清零
    """把"快递工具"的调用计数清零，保证「第一次必失败」这个设定每题都重新生效。"""
    _flaky_state["n"] = 0  # 归零


def query_package(tracking_no: str) -> str:   # tracking_no = 快递单号，自己起的参数名
    """查询快递单号的物流状态（本地模拟数据，没有真接快递公司接口）。用户问我的快递、包裹到哪了时使用。参数 tracking_no 是快递单号。"""
    _flaky_state["n"] += 1                 # 每被调一次就 +1
    if _flaky_state["n"] == 1:             # 第一次调用：模拟网络抖动，故意失败
        return "查询失败：网络连接超时（临时故障），请再重试一次。"   # ★明说"请再重试"，模型才会去重试
    # ★Day55 补：返回里加上"模拟数据"四个字，跟 web_search 的写法保持一致。
    #   原因：这个工具不管传什么单号都答同一句，介绍给别人/面试官时若不主动说明，
    #   一旦被追问"数据哪来的"就会很难看。主动标出来反而说明你懂 Mock 和真实数据的边界。
    return f"快递 {tracking_no}：已到达【北京转运中心】，预计明天送达。（模拟数据，非真实物流）"


# ========== 工具 8：记住一件事（★2026-10-08 新增，接上记忆模块）==========
# ★这个工具和前面 7 个最大的不同：它不是"查外面"，是"写自己家里"。
#   前面 7 个都是把外部信息取回来给模型看；这个是把模型判断"值得记"的话，
#   写进 memory.py 的长期记忆库（ChromaDB），下次换个新对话还能被 recall 出来。
# ★为什么做成"工具"让模型自己决定存什么，而不是每轮无脑全存？
#   因为无脑全存会把"今天天气怎么样"这种废话也塞进库，越存越脏，
#   recall 回来的全是噪音。做成工具 = 让模型自己判断"这句话以后还用得上吗"。
#   面试可以这么讲："我把'记什么'的决策权交给了模型本身，而不是写死规则。"
def remember_fact(text: str) -> str:    # text = 要记住的那句话，自己起的参数名
    """把用户透露的、值得长期记住的事实存进记忆库；下次新对话还能想得起来。

    什么时候用：用户说了关于他自己的、以后还用得上的信息 —— 比如名字、喜好、
    所在城市、正在做的项目、正在找什么工作。
    不要存：一次性的问题、闲聊、跟用户本人无关的信息、密码一类的敏感内容。
    参数 text：要记住的那句话，用第三人称写，例如「用户的名字叫小徐」。
    """
    text = (text or "").strip()             # strip() = 去掉首尾空白；(text or "") 防的是传进来是 None
    if not text:                            # 空话不存，直接给个明确回复
        return "这次没有收到要记住的内容，没有存。"
    # ★延迟导入：这一句写在函数【里面】而不是文件开头。
    #   因为 import memory 要多花约 1.8 秒（它带着 chromadb），而 edge_cases.py、
    #   test_scenarios.py 这些脚本也要 import 本文件 —— 它们用不到记忆，不该陪着一起慢。
    #   写在函数里 = 只有真的调这个工具时才付这 1.8 秒，而且只付一次（Python 会缓存已导入的模块）。
    from memory import get_long_term_memory
    fid = get_long_term_memory().add_fact(text)   # 存进共享的那个记忆库，拿回编号
    return f"已记住（编号 {fid}）：{text}"


# ========== 工具清单：全项目唯一的一份（★2026-10-07 合并后）==========
# ★★ 这一行是【全项目唯一的工具清单】。谁要用工具，都从这里拿，不许自己再写一份：
#     · agent_graph.py（网页 8501 那条路）→ from tools import TOOLS
#     · api.py        （接口 8000 那条路）→ from tools import TOOLS
#     · ui.py         （侧边栏列工具名）   → 从 agent_graph 再拿一次，但源头还是这里
# ★ 合并前是什么样（这话可以直接说给面试官听）：
#   "我项目里工具清单曾经有两份 —— 一份在 tools.py，一份在 agent_graph.py，
#    是两天分别写的，后来越加越不一样。结果是同一个 Agent，走网页能查快递，
#    走接口却不能读文件。我发现之后把它们合并成唯一一份，两条路都从这里导入。"
# ★ 为什么是 list（列表）不是 dict（字典）？
#   model.bind_tools(TOOLS) 和 ToolNode(TOOLS) 本机实测都只吃 list。
#   原计划里写 {"search": web_search, ...} 这种字典，传进去会报错。
# ★ 为什么列表里不带括号？
#   装的是"函数本身"。一加括号就成了"当场调用这个函数"，那是另一回事。
# ★★ 这一行必须写在 TOOLS【下面】，因为它要用 TOOLS 来生成。
#   普通写法 TOOL_MAP = {"web_search": web_search, ...} 要手写 8 遍，加一个工具就得多写一行，
#   早晚会漏。字典推导式 {t.__name__: t for t in TOOLS} 意思是"把清单里每个函数
#   按它自己的名字做成对照表"，加工具时这里一个字都不用动。
TOOLS = [web_search, calculate, add, get_time, get_weather, read_file, query_package, remember_fact]
#         联网搜索    算数学    相加   查时间    查天气     读文件    查快递      记住事实  ← 一共 8 个

# ★2026-10-08 新增：工具名 -> 函数 的对照表。
#   为什么需要它？下面第 8 个工具清单是给"模型"看的名字，而自愈节点拿到的
#   也是模型给的"工具名字符串"，得靠这张表把名字换回真正的函数才能调用。
TOOL_MAP = {t.__name__: t for t in TOOLS}


# ========== 自测：直接运行本文件才执行（被别人 import 时不执行）==========
if __name__ == "__main__":                  # __name__ = 内置变量，固定叫法；值是 "__main__" 说明是直接运行
    print("=== 逐个调用七个工具（看效果）===")
    print("1 搜索：", web_search("大模型 Agent 是什么"))
    print("2 计算：", calculate("2 + 3 * 4"))            # 正常算式
    print("3 计算：", calculate("(10 - 4) / 2"))          # 带括号的
    print("4 计算：", calculate("-5 + 2"))                # 带负号的
    print("5 计算：", calculate("1 / 0"))                 # 除以零，看报错长什么样
    print("6 危险：", calculate("__import__('os').system('echo 被攻击了')"))   # 危险输入，必须被挡
    print("7 加法：", add(5, 3))                          # ★2026-10-07 从 agent_graph.py 搬来的：两数相加
    print("8 时间：", get_time())                          # 不传参数，用默认值 ""
    print("9 时间：", get_time("x"))                       # 传一个没用的参数，看是否照样能跑
    print("10 天气：", get_weather("北京"))                 # Day51 接上真实数据：查天气（不再是假数据）
    print("11 文件：", read_file("tools.py"))              # Day53 新加的：读本目录里的文件，只给前 500 字
    print("12 穿越：", read_file("../../../windows/win.ini"))   # ★路径穿越，必须被拒绝
    print("13 没有：", read_file("这个文件肯定不存在_abc123.txt"))  # ★文件不存在，也必须返回一句人话
    print("=== 快递工具（故意失败一次）===")
    reset_flaky()                                        # 先清零，模拟"每道题开跑前"
    print("第一次：", query_package("SF1234567890"))       # ★必定失败，看它怎么说
    print("第二次：", query_package("SF1234567890"))       # 这次正常返回
    print("=== 工具清单 ===")
    print("类型：", type(TOOLS).__name__)                  # 打印出来应该是 list
    print("工具名：", [t.__name__ for t in TOOLS])          # __name__ = 函数自己的名字
    print("个数：", len(TOOLS))                            # ★2026-10-08 起是 8（10-07 合并时是 7，最初是 5）
    # ↑ [t.__name__ for t in TOOLS] 叫"列表推导式"，意思是"把每个函数的名字取出来组成一个新列表"
    #   这个写法 Day45 会用到，今天先看一眼，不要求你会写。

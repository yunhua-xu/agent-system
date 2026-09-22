
# -*- coding: utf-8 -*-
# 上面这行是告诉 Python：这个文件用 UTF-8 编码保存（里面有中文），固定写法，必须放第一行
"""
retry_utils.py —— 工具纠错 / 自愈重试

=== 今天要解决的 5 个原始 bug（原计划里的错，这里全部改掉）===
bug1: args = fix_args(args, e)          -> fix_args 原来只有一个参数，却传了 2 个；而且这个函数根本没定义
    改法：正式定义成 fix_args(args, err_msg) 两个参数，函数体真的能根据报错信息改参数
bug2: fallback(args)                    -> fallback 也没定义
    改法：正式定义成 fallback(tool_name, args)，返回一个字符串
bug3: time.sleep(1)                     -> 没有 import time
    改法：文件顶部 import time
bug4: return "调用失败" 写在 for 循环外面  -> 循环里一旦 return 过，外面的永远执行不到（死代码）
    改法：return 只写在 try 里面（成功才返回），失败继续循环；循环彻底走完才走 fallback
bug5: 重试间隔固定 1 秒                  -> 不好，服务器可能正忙，固定间隔会一起挤上去
    改法：指数退避 time.sleep(WAIT_UNIT * (WAIT_BASE ** i))，也就是 1 秒、2 秒、4 秒，越等越久

=== 名词解释（零基础先看这里）===
retry   = 重试的意思，自己起的名字
backoff = 退避的意思，指"失败后等一会儿再来"，指数退避就是每次等的时间翻倍
fallback= 备用方案、退路的意思，指主力工具彻底用不了时换的备用办法
args    = arguments 的缩写，参数的意思，这里指传给工具（函数）的那包参数
err_msg = error message 的缩写，报错信息的意思
"""

import time                 # time = 时间模块，固定写法；用来做"等几秒再重试"
import difflib              # difflib = 字符串相似度模块，固定写法；用来把写错的城市名纠正成最像的那个

# WAIT_BASE = 退避的"底数"，自己起的变量名
# ★底数必须大于 1，退避才是&quot;越等越久&quot;；写成 0.02（小于 1）就变成&quot;越等越短&quot;，概念就反了
# 2 表示：每次等待时间翻倍 —— 第 1 次重试等 2**0=1 秒，第 2 次等 2**1=2 秒，第 3 次等 2**2=4 秒
WAIT_BASE = 2


# WAIT_UNIT = 等待时间的&quot;单位&quot;，自己起的变量名
# 每次等待 = WAIT_UNIT × (WAIT_BASE 的 i 次方)；真实项目里用 1 秒
# ★演示想跑快时，只调这个&quot;单位&quot;，千万别去动上面的&quot;底数&quot;（一动方向就反了）
WAIT_UNIT = 1

# REQUIRED_DEFAULTS = 必须有的参数 + 它缺省时补什么值，自己起的变量名
# 作用：报错说"缺 city"，我们就从这里查出来补上 "北京"
REQUIRED_DEFAULTS = {
    "city": "北京",         # city = 城市的意思，缺了就默认当成北京
    "days": 1,              # days = 天数的意思，缺了就默认查 1 天
}

# KNOWN_CITIES = 系统认识的城市名单，自己起的变量名；用它来猜用户写错的城市最像哪一个
KNOWN_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都"]

# ATTEMPT_COUNT = 记录每个假工具被调用了几次，自己起的变量名
# 只为了让演示函数"前几次故意失败、后面成功"，真实项目里没有这个东西
ATTEMPT_COUNT = {}


def _count(name):
    """（内部小工具）每被调用一次就 +1，返回这是第几次。前面的下划线表示"内部用，外面别管"。"""
    ATTEMPT_COUNT[name] = ATTEMPT_COUNT.get(name, 0) + 1     # 取旧值 +1，没有就当 0
    return ATTEMPT_COUNT[name]                               # 返回当前是第几次


# =====================================================================
# (a) fix_args —— 根据报错信息，修参数
# =====================================================================
def fix_args(args, err_msg):
    """
    作用：拿到"上一次为什么失败"的报错信息，试着把参数改对，返回修好的新参数。
    参数 args    = 原来那包参数（字典）
    参数 err_msg = 报错信息（字符串，例如 "TypeError: ... missing ... 'city'"）
    返回：修好的新字典（如果修不了，就原样返回一份）
    """
    new_args = dict(args)          # dict() 复制一份，不改动原来那包参数（好习惯）
    text = err_msg.lower()         # lower() = 变小写，这样 "TypeError" 和 "typeerror" 都能匹配上

    # ---------- 情况 1：缺参数 ----------
    # "missing" 是缺少的意思，"keyerror" 是字典里没有这个键的报错名
    if "missing" in text or "keyerror" in text or "缺少参数" in err_msg:
        for name in REQUIRED_DEFAULTS:                     # 遍历每一个"应该有的参数"
            # 报错信息里提到了这个参数名，而且参数包里确实没有它 -> 补默认值
            if name in err_msg and name not in new_args:
                new_args[name] = REQUIRED_DEFAULTS[name]   # 补上默认值

    # ---------- 情况 2：参数类型不对 ----------
    # "typeerror" 是类型错误的报错名；"类型" 是中文提示
    elif "typeerror" in text or "类型" in err_msg:
        for key in list(new_args.keys()):                  # list() 复制一份键，边遍历边改字典才安全
            value = new_args[key]                          # value = 值的意思，先取出来
            # isdigit() = 判断是不是"纯数字的字符串"，比如 "3" 是，True 不是
            if isinstance(value, str) and value.isdigit():
                new_args[key] = int(value)                 # int() = 转成整数，把 "3" 变成 3

    # ---------- 情况 3：名字写错（比如城市名不存在）----------
    elif "not found" in text or "不存在" in err_msg:
        city = new_args.get("city")                        # get() = 取出来，没有就返回 None（不会报错）
        if isinstance(city, str) and city not in KNOWN_CITIES:
            # get_close_matches = 找出最像的匹配项，固定用法
            # cutoff=0.5 表示相似度要到 50% 才算，太低会乱猜
            match = difflib.get_close_matches(city, KNOWN_CITIES, n=1, cutoff=0.5)
            if match:                                      # match 是列表，非空表示找到了
                new_args["city"] = match[0]                # [0] 取第一个，也就是最像的那个

    # 有改动才打印，让演示的时候看得见"到底修了什么"
    if new_args != args:
        print(f"     [fix_args] 参数已修正：{args} -> {new_args}")

    return new_args               # 返回修好的参数（改不动就返回和原来一模一样的内容）


# =====================================================================
# (b) fallback —— 重试全失败了，换备用方案
# =====================================================================
def fallback(tool_name, args):
    """
    作用：一个工具重试好几次都失败，就调用它，返回一个"兜底"的结果。
    参数 tool_name = 工具（函数）的名字，字符串
    参数 args      = 最后一次用的参数（字典）
    返回：字符串（备用结果）
    """
    print(f"     [fallback] 工具 {tool_name} 彻底用不了，换成备用方案")

    # 按工具名里有没有某个词，给不同的备用结果
    if "weather" in tool_name:                                  # 天气类工具
        city = args.get("city", "未知城市")                      # 取不到城市就写"未知城市"
        return f"（备用数据）{city}：晴，26℃（来自本地缓存）"      # f"..." 是拼字符串，{} 里放变量
    if "search" in tool_name:                                   # 搜索类工具
        return "（备用数据）搜索服务不可用，返回本地知识库里的旧结果"
    return f"（备用数据）工具 {tool_name} 暂时不可用，请稍后再试"    # 其他情况：统一兜底


# =====================================================================
# (c) call_with_retry —— 核心：失败 -> 修参数 -> 等一会儿 -> 再试
# =====================================================================
def call_with_retry(func, args, max_retry=3):
    """
    作用：调用一个工具，失败了就修参数、等一等再重试，最多重试 max_retry 次；
          还失败就换备用方案 fallback。
    参数 func      = 要调用的函数（工具）
    参数 args      = 传给这个函数的参数（字典）
    参数 max_retry = 最多重试几次（默认 3），注意：加上第一次调用，一共最多跑 max_retry+1 次
    返回：工具的结果（字符串），或者备用方案的结果（字符串）
    """
    tool_name = func.__name__        # __name__ = 函数的"名字"，固定写法；用它当工具名
    current_args = dict(args)        # current_args = 当前参数，复制一份，后面会被 fix_args 改
    last_error = None                # 记一下最后一次的报错，方便最后打印

    # range(max_retry + 1) 会生成 0,1,2,3；i=0 是第一次调用，i=1/2/3 是 3 次重试
    for i in range(max_retry + 1):
        try:
            result = func(**current_args)    # ** 表示"把字典拆开当参数传进去"，固定写法
            return result                    # 成功：就地返回，函数立刻结束（这就是 return 该在的位置）
        except Exception as e:               # except = 捕获异常；as e 把报错对象存到 e 里
            last_error = e                   # 存下这次报错
            print(f"     第 {i + 1} 次调用失败：{type(e).__name__}: {e}")

            # 把报错信息交给 fix_args，让它想办法把参数改对；改不动就原样返回
            current_args = fix_args(current_args, f"{type(e).__name__}: {e}")

            if i < max_retry:                # 还没到最后一次，就歇一会儿再重试
                wait = WAIT_UNIT * (WAIT_BASE ** i)        # ** 是"几次方"；i=0 等 1 倍基数，i=1 等 2 倍，i=2 等 4 倍
                print(f"     -> 等 {wait:g} 秒后重试（指数退避：{WAIT_UNIT:g}×{WAIT_BASE:g} 的 {i} 次方）")
                time.sleep(wait)             # sleep = 睡、等待的意思；让程序真的停几秒

    # 循环全部跑完还没 return，说明 max_retry 次重试都失败了 -> 走备用方案
    print(f"     重试 {max_retry} 次仍然失败，最后一次报错：{type(last_error).__name__}: {last_error}")
    return fallback(tool_name, current_args)     # 注意：这个 return 在循环【外面】，是兜底的出口


# =====================================================================
# (d) 5 个假工具函数 —— 故意会失败，用来演示 5 种错误场景
#     注意：真实的项目里这些是调 API；这里造假的是为了演示，不去真联网，省时间
# =====================================================================

def api_slow_tool(city):
    """场景1：接口超时。前 2 次调用故意超时，第 3 次成功。参数本身没问题，只需要重试。"""
    n = _count("api_slow_tool")                       # 这是第几次被调用
    if n <= 2:                                        # 前 2 次故意失败
        raise TimeoutError("接口响应超时（模拟）")      # raise = 抛出异常；TimeoutError = 超时错误
    return f"[场景1] {city} 今天晴，26℃（第 {n} 次调用才成功）"


def weather_tool(city, unit="c"):
    """场景2：参数缺失。调用时没给 city，Python 自己就会报 missing，fix_args 补上默认值。"""
    _count("weather_tool")
    # 能走到这里说明 city 已经有了（缺的话上面调用时就报错了）
    return f"[场景2] {city} 天气查询成功，单位={unit}"


def get_forecast_tool(city, days):
    """场景3：参数类型错。days 应该传整数，演示时故意传字符串 "3"。"""
    _count("get_forecast_tool")
    if not isinstance(days, int):                                  # isinstance = 判断是不是某种类型
        raise TypeError(f"argument 'days' has wrong type: {type(days).__name__}, expected int")
    return f"[场景3] {city} 未来 {days} 天预报查询成功"


def weather_by_city_tool(city):
    """场景4：城市名不存在。演示时故意把"北京"写成"北景"，靠纠错猜回正确的城市。"""
    _count("weather_by_city_tool")
    if city not in KNOWN_CITIES:                                   # 不在名单里 -> 报错
        raise ValueError(f"city not found: {city}")
    return f"[场景4] {city} 天气查询成功"


def net_weather_tool(city):
    """场景5：网络断。每次都失败，参数怎么修都没用，最后只能走备用方案。"""
    _count("net_weather_tool")
    raise ConnectionError("网络断了，连不上服务器（模拟）")          # ConnectionError = 连接错误


# =====================================================================
# (e) __main__ —— 逐个跑 5 个场景
#     只有直接运行这个文件（python retry_utils.py）才会执行，被别人 import 时不执行
# =====================================================================
if __name__ == "__main__":

    # 演示专用：只把&quot;等待单位&quot;调小，底数 WAIT_BASE 一个字都不动
    # （不然 5 个场景要真等十几秒；★底数一动，&quot;越等越久&quot;就变成&quot;越等越短&quot;了，那就演示反了）
    # 真实项目里这一行不要写，用文件顶部的 WAIT_UNIT = 1（1秒/2秒/4秒）
    WAIT_UNIT = 0.02

    print("=" * 60)
    print("场景 1：API 超时（参数没错，靠重试自己恢复）")
    print("=" * 60)
    print("最终结果：", call_with_retry(api_slow_tool, {"city": "上海"}))

    print()
    print("=" * 60)
    print("场景 2：参数缺失（调用时少了 city，fix_args 补默认值）")
    print("=" * 60)
    print("最终结果：", call_with_retry(weather_tool, {"unit": "c"}))

    print()
    print("=" * 60)
    print("场景 3：参数类型错（days 传成了字符串 \"3\"，fix_args 转成整数）")
    print("=" * 60)
    print("最终结果：", call_with_retry(get_forecast_tool, {"city": "广州", "days": "3"}))

    print()
    print("=" * 60)
    print("场景 4：城市名不存在（\"北景\" 写错了，fix_args 猜成最像的城市）")
    print("=" * 60)
    print("最终结果：", call_with_retry(weather_by_city_tool, {"city": "北景"}))

    print()
    print("=" * 60)
    print("场景 5：网络断（参数怎么修都没用，重试 3 次后走 fallback）")
    print("=" * 60)
    print("最终结果：", call_with_retry(net_weather_tool, {"city": "深圳"}))

    print()
    print("=" * 60)
    print("5 个场景全部跑完")
    print("=" * 60)
    # 演示时为了快，把 WAIT_UNIT 调成了 0.02 秒；真实项目里单位是 1 秒，等的时间就是下面这样
    print("真实项目里的等待时间：第1次重试 1 秒、第2次 2 秒、第3次 4 秒（1 × 2 的 0/1/2 次方）")

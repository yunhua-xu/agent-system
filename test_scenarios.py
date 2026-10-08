# test_scenarios.py —— Day46：5 种场景 × 3 个问题 = 15 条测试，跑完自动判 PASS / FAIL
# 核心思想：跑之前先写下"这题应该调哪个工具"，跑完拿实际结果去比。
#          没有"期望值"的测试就是走过场 —— 模型自己编个答案你也看不出来。

from agent_graph import app                           # app = Day45 建好的图
from tools import reset_flaky                         # ★2026-10-07 改：reset_flaky 跟着 query_package 一起搬去 tools.py 了（唯一来源，别再从这里 import）
from langchain_core.messages import HumanMessage      # HumanMessage = 人类（用户）说的那条消息

# ============ 一、场景表 ============
# 每一项是 3 个东西：(场景名, 问题, 期望调用的工具名集合)
# 集合（set）用 {} 写，比如 {"get_time"}；★空集合必须写 set()，不能写 {}（{} 是空字典，不是空集合）
SCENARIOS = [
    # ---- 场景1：纯对话（不该调任何工具，模型自己用嘴回答就行）----
    ("纯对话",   "你好，用一句话介绍你自己",                  set()),
    ("纯对话",   "谢谢你，你刚才帮了大忙",                    set()),
    ("纯对话",   "你叫什么名字？",                            set()),

    # ---- 场景2：单个工具（只该调 1 个工具，精确到名字）----
    ("单个工具", "现在几点？",                                {"get_time"}),
    ("单个工具", "5+3等于几？",                               {"add"}),
    ("单个工具", "北京今天天气怎么样？",                        {"get_weather"}),

    # ---- 场景3：2 个以上工具串联（一条问题里要调多个工具）----
    ("多工具串联", "现在几点？再加5和3",                        {"get_time", "add"}),
    ("多工具串联", "帮我算一下 12*12，再告诉我现在几点",          {"calculate", "get_time"}),
    ("多工具串联", "北京天气怎么样？顺便算一下 100-37",           {"get_weather", "calculate"}),

    # ---- 场景4：需要重试（工具第一次会失败，模型该看到报错再试一次）----
    ("需要重试", "帮我查一下快递单号 SF1234567890 到哪了",       {"query_package"}),
    ("需要重试", "查下快递 YT9876543210 的物流",                {"query_package"}),
    ("需要重试", "我的包裹单号 789456123 现在到哪了？",          {"query_package"}),

    # ---- 场景5：超出能力范围（工具箱里没有的能力，期望就是"不调工具"，老实说做不到）----
    ("超出能力", "帮我订一张去北京的机票",                      set()),
    ("超出能力", "帮我把这封辞职信发给我老板",                   set()),
    ("超出能力", "帮我叫一份外卖，要一份牛肉面",                 set()),
]

# 「需要重试」这类场景，光看"调了哪个工具"不够，还要看"调了几次"。
# 下面这张表：问题 → 至少要调几次才算过了。没写的问题默认 0 次。
EXPECT_MIN_CALLS = {
    "帮我查一下快递单号 SF1234567890 到哪了": 2,      # 第一次网络超时 → 该再试一次，所以至少 2 次
    "查下快递 YT9876543210 的物流": 2,                 # 同上
    "我的包裹单号 789456123 现在到哪了？": 2,          # 同上
}

# ---------- 写这份测试时踩到的 3 个坑（记下来，别重复踩）----------
# 坑1：「需要重试」这个场景，原执行计划写的是第 4 个场景 = "混着来"，逐行标注写的是"重试"。
#      用"重试"是对的 —— 但前提是工具箱里得有一个"会失败的工具"。
#      所以我在 agent_graph.py 里加了 query_package：它第一次调用必定返回"网络超时"，
#      第二次才成功。这才能真的测出"模型看到报错后会不会再试一次"。
#      注意它是"有状态"的（靠 _flaky_state 这个字典记次数），所以每道题开跑前要 reset_flaky() 清零，
#      否则第 2 道题一上来就成功了，测不出重试。
#      ★2026-10-07 补：query_package 和 reset_flaky 后来从 agent_graph.py 搬到了 tools.py
#        （工具和它的状态都归工具箱管，agent_graph.py 只管画图），所以第 5 行的 import 也改了。
#
# 坑2：「超出能力」场景，问题里千万别带"明天 / 今天"这类词。
#      我实测：问"帮我订一张【明天】去北京的机票"，模型会为了算"明天是几号"去调 get_time，
#      于是这条就被判 FAIL —— 但模型的这个行为其实不算错，是"期望值"写歪了。
#      教训：期望值本身要想清楚，否则测试会误报。这就是"只看有没有报错"的测试等于没测的原因。
#
# 坑3：「纯对话」里的"谢谢你，你刚才帮了大忙"，模型的回答是"我这边没有保留之前的对话记录"。
#      这不算 bug —— 每次 invoke 都是全新的一次对话，短期记忆没跨轮保留。
#      要让它记住，是 Day47「双记忆系统」的活。
#
# ---------- 怎么改 prompt 让它更稳（建议，已实测数据支撑）----------
# 在 agent_graph.py 里启用那段 SYSTEM_PROMPT（文件里写了怎么开），效果：
#   同一个问题"帮我订一张明天去北京的机票"，各跑 5 次：
#     不加 system prompt → 3/5 次乱调了 get_time
#     加了 system prompt → 0/5 次乱调
# 关键就一句："如果工具清单里没有对应的工具，直接说明你做不到，不要为了凑数去调用无关的工具。"
# 另一条经验：工具越全，Agent 越不容易绕圈。
#   工具箱里只有 add 的时候，让它算 12*12，它会自己拆成 12+12、24+24… 连调 4 次（白烧 token）。
#   补上 calculate 之后，一次就调对了。


# ============ 二、跑一条 ============

def run_one(question, limit=10):                      # question = 问题文本；limit = 循环上限
    """把一个问题丢给 Agent，返回 (最终回答, 这轮调过的工具名列表)。"""
    try:
        reset_flaky()                                 # 先清零，保证"第一次必失败"这个设定每题都生效
    except Exception:                                 # 万一没有这个函数（换工具箱了）也不能崩
        pass                                          # 忽略，继续跑

    r = app.invoke(                                   # invoke = 调用，让图跑起来
        {"messages": [HumanMessage(content=question)]},   # 把问题包成消息列表传进去
        config={"recursion_limit": limit},                # ★循环上限写在这里，防止模型绕圈烧钱
    )

    names = []                                        # 用来装"这轮调过的工具名"，按顺序
    for m in r["messages"]:                           # ★★遍历整轮的所有消息，绝不能只看最后一条
        for tc in (getattr(m, "tool_calls", None) or []):   # tc = tool_call，取这条消息里的工具调用列表（没有就是空）
            names.append(tc["name"])                  # tc 是个字典，用 ["name"] 取出工具名
    # 为什么必须遍历全部消息：
    #   工具执行完，控制权回到 agent 再想一次，最后一条消息一定是"最终回答"，
    #   它的 tool_calls 是空列表 []。所以用 messages[-1] 判断"调没调工具"永远是错的（Day52 的评测脚本就栽在这）。

    answer = r["messages"][-1].content                # 最后一条的 content = 最终回答
    return (answer or ""), names                      # ★content 可能是 None（这轮只调工具没说话），所以要兜底


# ============ 三、跑全部 ============

def run_scenarios():                                  # 跑完 15 条，逐条打印 PASS / FAIL
    ok_count = 0                                      # 过了几条
    total = len(SCENARIOS)                            # 一共几条

    for name, question, expect in SCENARIOS:          # 逐条取出来：场景名 / 问题 / 期望工具集合
        try:                                          # ★包 try：一条崩了不影响后面
            answer, used_list = run_one(question)     # 跑这一条
            used_set = set(used_list)                 # 把实际调过的工具名转成集合，好和期望比

            min_calls = EXPECT_MIN_CALLS.get(question, 0)     # 这题至少要调几次
            tool_ok = (used_set == expect)            # ★硬标准1：调过的工具集合，和期望完全一致（多一个少一个都算错）
            count_ok = (len(used_list) >= min_calls)  # ★硬标准2：调用次数够不够（专治"需要重试"）
            ok = tool_ok and count_ok                 # 两个都满足才算过

            if ok:                                    # 过了就 +1
                ok_count += 1

            print(f"[{name}] {question}")
            print(f"   期望工具 {sorted(expect) if expect else '[]'} / 实际工具 {sorted(used_set) if used_set else '[]'}"
                  f" / 实际调用 {len(used_list)} 次")
            print(f"   判定 → {'PASS' if ok else 'FAIL'}"
                  + ("" if count_ok else f"（次数不够：至少要 {min_calls} 次）"))
            print(f"   回答：{(answer or '')[:60]}")   # 只打印前 60 字，太长刷屏
            print()                                   # 空一行好看
        except Exception as e:                        # 这一条崩了
            print(f"[{name}] {question}")
            print(f"   崩了：{type(e).__name__}: {e}")   # ★打印异常类型和原因，不要吞掉
            print()                                   # 空一行

    print(f"结果：{ok_count}/{total} 通过")             # 最后给通过数
    return ok_count, total                            # 顺手返回，方便别的脚本调用


if __name__ == "__main__":                            # ★只有直接运行本文件才跑（被 import 时不跑，避免误触发花钱）
    run_scenarios()                                   # 开跑

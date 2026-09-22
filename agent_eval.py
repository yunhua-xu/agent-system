# agent_eval.py = Agent 评测脚本；eval = evaluation 的缩写，意思是"评测/打分"
# 干什么用：拿一批【固定好的问题】挨个问 Agent，看它该调工具的时候到底调没调，
#           最后算出一个"正确率"。面试时这叫"Agent 评测"，是项目二的重要加分项。
#
# ★ 运行前要保证 agent_graph.py 和 tools.py 在本文件同一层文件夹
# ★ 运行命令：python agent_eval.py

import sys                                   # sys = system 的缩写，用来改输出编码


# ---------------------------------------------------------------------------
# 【第 0 步】解决 Windows 中文乱码：让 print 用 utf-8 输出
# ---------------------------------------------------------------------------
# 本机是 Windows，命令行默认编码是 GBK，遇到特殊符号会报 UnicodeEncodeError。
# 加这两行就稳了；顺手也不要在 print 里放 emoji。
try:                                         # 试着改
    sys.stdout.reconfigure(encoding="utf-8")  # reconfigure = 重新配置；把标准输出改成 utf-8
except Exception:                            # 老版本 Python 可能没这个方法
    pass                                     # pass = 什么都不做（占位，语法上必须有）

from agent_graph import app                  # ★导入 Day45 编译好的 Agent 图


# ---------------------------------------------------------------------------
# 【第 1 步】评测任务表
# ---------------------------------------------------------------------------
# 每一行是：(问题, 期望类型, 期望工具名)
#   - 期望类型 "工具" = 这题应该去调工具；"直接" = 这题应该直接回答，不该调工具
#   - 期望工具名 填 None 表示"调了工具就算对，不挑具体哪个"；填名字则要求真的用到这个工具
TASKS = [                                              # TASKS = 任务表
    ("现在几点了？",           "工具", "get_time"),      # 该调时间工具
    ("帮我算一下 5+3 等于几",   "工具", "calculate"),     # 该调计算工具
    ("北京天气怎么样？",        "工具", "get_weather"),   # 该调天气工具
    ("现在几点？再算一下 2+3*4", "工具", None),           # 该调工具（可能调好几个，不挑具体哪个）
    ("你好，用一句话介绍你自己", "直接", None),            # 闲聊，不该调工具
    ("用一句话解释什么是人工智能", "直接", None),           # 常识问答，不该调工具
]


# ---------------------------------------------------------------------------
# 【第 2 步】判断"这轮到底调没调工具" —— 本文件最关键的一个函数
# ---------------------------------------------------------------------------
def count_tool_calls(messages):
    """
    ★★ 本机实测的血泪教训，这段注释请务必看完 ★★
    曾经有人这样判断"这轮调没调工具"：
        last = messages[-1]                                # 取最后一条消息
        is_tool = hasattr(last, "tool_calls") and last.tool_calls
    结果正确率永远是 1/3（6 条里只对 2 条），死活查不出原因。
    原因：Agent 最后那条 AIMessage（就是"生成回答"那条）的 tool_calls 是【空列表 []】！
          工具调用信息在【中间】那条 AIMessage 上，不在最后一条上。
          所以用 messages[-1] 判断，永远得到"没调工具"，
          于是"该调工具"的题全判错、"该直接答"的题全判对。
    正确做法：遍历【所有】消息，把每条的 tool_calls 长度累加起来。
    """
    total = 0                                            # total = 总数，计数器从 0 开始
    for message in messages:                             # 一条一条看过去
        calls = getattr(message, "tool_calls", None) or []   # getattr = 取属性；取不到就当作空列表
        total = total + len(calls)                       # len = length，长度；累加
    return total                                         # 返回总次数


def collect_tool_names(messages):
    """收集这轮用到了哪些工具名（去重，保持出现顺序）"""
    names = []                                           # names = 名字列表，先空着
    for message in messages:                             # 遍历所有消息（同样不能用 messages[-1]）
        calls = getattr(message, "tool_calls", None) or []   # 这条消息里的工具调用
        for call in calls:                               # 一次可能调好几个
            if isinstance(call, dict):                   # 字典形式就取 "name" 键
                name = call.get("name")
            else:                                        # 对象形式就取 .name 属性
                name = getattr(call, "name", None)
            if name and name not in names:               # 有名字且没记过
                names.append(name)                       # 记下来
    return names                                         # 返回


# ---------------------------------------------------------------------------
# 【第 3 步】跑一条任务，返回打分结果
# ---------------------------------------------------------------------------
def judge_one(question, expect_type, expect_tool):
    """跑一个问题，返回一个字典，里面装着"实际调了什么、对了没有" """
    try:                                                 # 包住调用，Agent 崩了不能让整个评测挂掉
        result = app.invoke({"messages": [{"role": "user", "content": question}]})   # 真的调用 Agent
    except Exception as e:                               # e = error，错误原因
        return {                                         # 出错就原样返回一条"失败记录"
            "question": question, "expect_type": expect_type, "expect_tool": expect_tool,
            "actual_type": "出错", "used_tools": [], "error": str(e),
            "type_ok": False, "tool_ok": False,
        }

    messages = result["messages"]                        # Agent 这轮产生的全部消息
    calls = count_tool_calls(messages)                   # ★遍历累加，得到调用次数
    used_tools = collect_tool_names(messages)            # 实际用到的工具名

    actual_type = "工具" if calls > 0 else "直接"          # 调了就是"工具"，没调就是"直接"
    type_ok = (actual_type == expect_type)               # 类型判断对不对

    if expect_tool:                                      # 这题指定了必须用某个工具
        tool_ok = (expect_tool in used_tools)            # 期望的工具名有没有出现在实际用的里面
    else:
        tool_ok = True                                   # 没指定工具名，这项不扣分

    return {                                             # 把结果打包成字典返回
        "question": question,
        "expect_type": expect_type,
        "expect_tool": expect_tool,
        "actual_type": actual_type,
        "used_tools": used_tools,
        "error": "",
        "type_ok": type_ok,
        "tool_ok": tool_ok,
    }


# ---------------------------------------------------------------------------
# 【第 4 步】主流程：跑完所有任务，打印表格，算正确率
# ---------------------------------------------------------------------------
def main():
    """main = 主要的，程序的主入口函数"""
    print("=" * 78)                                      # 打印一条分隔线
    print("Agent 评测开始：一共 " + str(len(TASKS)) + " 条任务")
    print("=" * 78)

    rows = []                                            # rows = 行，装每条任务的打分结果
    for question, expect_type, expect_tool in TASKS:     # 一行一行遍历任务表
        row = judge_one(question, expect_type, expect_tool)   # 跑这一条
        rows.append(row)                                 # 存下来
        mark = "通过" if (row["type_ok"] and row["tool_ok"]) else "不通过"   # 两项都对才算通过
        print("")                                        # 空一行，看着清楚
        print("问题：" + question)
        print("  期望：" + expect_type + ("（指定工具 " + expect_tool + "）" if expect_tool else ""))
        print("  实际：" + row["actual_type"] + "（用到的工具：" + (", ".join(row["used_tools"]) or "无") + "）")
        print("  判定：" + mark)
        if row["error"]:                                 # 如果这题报错了，把原因打出来
            print("  错误：" + row["error"])

    # ---- 统计 ----
    total = len(rows)                                    # 总条数
    type_pass = 0                                        # "该不该调工具"判断对的条数
    tool_pass = 0                                        # "工具选得对不对"的条数
    all_pass = 0                                         # 两项都对的条数
    for row in rows:                                     # 遍历结果
        if row["type_ok"]:                               # 类型对
            type_pass = type_pass + 1                    # 计数 +1
        if row["tool_ok"]:                               # 工具选得对
            tool_pass = tool_pass + 1                    # 计数 +1
        if row["type_ok"] and row["tool_ok"]:            # 两个都对
            all_pass = all_pass + 1                      # 计数 +1

    print("")                                            # 空行
    print("=" * 78)
    print("评测结果汇总")
    print("=" * 78)
    print("1) 该不该调工具  判断正确：" + str(type_pass) + "/" + str(total) +
          "  正确率 " + format(type_pass / total * 100, ".1f") + "%")     # format 保留 1 位小数
    print("2) 工具选得对不对 判断正确：" + str(tool_pass) + "/" + str(total) +
          "  正确率 " + format(tool_pass / total * 100, ".1f") + "%")
    print("3) 综合（两项都过）正确：" + str(all_pass) + "/" + str(total) +
          "  正确率 " + format(all_pass / total * 100, ".1f") + "%")
    print("")
    print("面试话术：我的 Agent 在 " + str(total) + " 条评测任务上，" +
          "工具调用判断正确率 " + format(type_pass / total * 100, ".0f") + "%，" +
          "工具选择正确率 " + format(tool_pass / total * 100, ".0f") + "%。")


if __name__ == "__main__":                               # 只有直接运行本文件时才执行 main()
    main()

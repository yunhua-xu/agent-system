# eval = evaluation（评测/评估）的缩写；stats = statistics（统计）的缩写
# 这个脚本干一件事：把 logs/trace.jsonl 里的每一行读出来，算 4 个指标：
#   1) 请求总数 + 成功率
#   2) 工具调用率（多少请求真的调了工具）
#   3) 工具调用成功率（调了工具的请求里，多少是成功的）
#   4) 平均耗时；另外列出失败的问题清单、每个工具被调用的次数
# 运行方式：python eval_stats.py

# ---------- 导入 ----------
import json                                # 读日志要解析 JSON
import sys                                 # sys = system 的缩写，用来读"命令行传进来的参数"
from pathlib import Path                   # 处理路径
from collections import Counter            # Counter = 计数器，专门用来"数每个东西出现了几次"

# ---------- 找到日志文件 ----------
LOG_FILE = Path(__file__).resolve().parent / "logs" / "trace.jsonl"
# __file__ = 本脚本自己；.resolve() = 变成绝对路径；.parent = 所在文件夹

# ---------- 读日志 ----------
def load_logs(path: Path):
    """把 jsonl 文件读成一个字典列表。文件不存在就返回空列表，不让脚本报错崩掉。"""
    if not path.exists():                  # 文件不存在
        return []                          # 返回空列表
    rows = []                              # rows = 一行行日志
    with open(path, "r", encoding="utf-8") as f:   # 打开文件读；with 会自动关
        for line in f:                     # 一行一行读
            line = line.strip()            # 去掉行尾换行和空格
            if not line:                   # 空行
                continue                   # 跳过
            try:
                rows.append(json.loads(line))   # 解析成字典放进去
            except json.JSONDecodeError:   # 遇到坏行（比如写到一半断电）
                continue                   # 跳过，不影响其他行
    return rows                            # 返回全部记录

# ---------- 算指标 ----------
def summarize(rows):
    """输入日志列表，返回一个装好各项指标的字典。"""
    total = len(rows)                      # 总请求数
    if total == 0:                         # 一条日志都没有
        return None                        # 返回 None，让上层提示"还没数据"

    ok_rows = [r for r in rows if r.get("success")]        # 成功的那些行
    fail_rows = [r for r in rows if not r.get("success")]  # 失败的那些行
    ok_count = len(ok_rows)                # 成功条数
    fail_count = len(fail_rows)            # 失败条数

    tool_rows = [r for r in rows if r.get("tools_used")]   # "调用了工具"的那些行（tools_used 非空）
    tool_ok = [r for r in tool_rows if r.get("success")]   # 调了工具、并且成功

    # 平均耗时：sum 求和 / 个数
    elapsed_list = [r.get("elapsed", 0) for r in rows]     # 把每条的耗时取出来
    avg_elapsed = sum(elapsed_list) / total if total else 0   # 求和再除以总数

    # 每个工具分别被调用了几次（把所有行的 tools_used 摊平，再用 Counter 数）
    tool_counter = Counter()               # 建一个空计数器
    for r in rows:                         # 每一行
        for name in (r.get("tools_used") or []):   # 这行用到的每个工具名
            tool_counter[name] += 1        # 计数 +1

    return {                               # 把结果打包成字典返回
        "total": total,                    # 总请求数
        "ok": ok_count,                    # 成功数
        "fail": fail_count,                # 失败数
        "ok_rate": ok_count / total,       # 请求成功率
        "tool_rows": len(tool_rows),       # 调用了工具的请求数
        "tool_rate": len(tool_rows) / total,                  # 工具调用率
        "tool_ok_rate": (len(tool_ok) / len(tool_rows)) if tool_rows else 0.0,   # 工具调用成功率
        "avg_elapsed": avg_elapsed,        # 平均耗时
        "tool_counter": tool_counter,      # 各工具被调用次数
        "fail_questions": [r.get("question", "") for r in fail_rows],   # 失败的问题列表
    }

# ---------- 打印报告 ----------
def print_report(stats, log_file: Path):
    """把指标打印成人能看懂的样子。"""
    print("=" * 46)                        # 打印一条分隔线；"*" * 46 表示把 * 重复 46 次
    print("Agent 评测报告 / eval report")   # 标题
    print("日志文件:", log_file)            # 日志位置
    print("=" * 46)
    if stats is None:                      # 没有数据
        print("还没有日志。先跑几次 /chat 再来统计。")
        return                             # 直接结束
    print(f"请求总数      : {stats['total']}")
    print(f"成功 / 失败   : {stats['ok']} / {stats['fail']}")
    print(f"请求成功率    : {stats['ok_rate']:.1%}")      # :.1% 表示按百分比显示、保留 1 位小数
    print(f"调用了工具的  : {stats['tool_rows']} 条")     # 有多少请求真的调了工具
    print(f"工具调用率    : {stats['tool_rate']:.1%}")
    print(f"工具调用成功率: {stats['tool_ok_rate']:.1%}")   # 调了工具的请求里成功的比例
    print(f"平均耗时      : {stats['avg_elapsed']:.3f} 秒")
    print("-" * 46)
    if stats["tool_counter"]:              # 如果有工具被调用过
        print("各工具被调用次数：")
        for name, cnt in stats["tool_counter"].most_common():   # most_common() 按次数从多到少排
            print(f"  - {name}: {cnt} 次")
    else:
        print("各工具被调用次数：一个工具都没被调用过")
    print("-" * 46)
    if stats["fail_questions"]:            # 有失败的问题
        print("失败的问题清单：")
        for q in stats["fail_questions"]:
            print(f"  - {q}")
    else:
        print("失败的问题清单：无")
    print("=" * 46)

# ---------- 主流程 ----------
def main():
    """脚本入口：允许用命令行指定日志文件，不指定就用默认位置。"""
    # sys.argv 是命令行参数列表：argv[0] 是脚本名，argv[1] 是第一个参数
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else LOG_FILE   # 传了参数就用参数，没传就用默认
    rows = load_logs(path)                 # 读日志
    stats = summarize(rows)                # 算指标
    print_report(stats, path)              # 打印报告

if __name__ == "__main__":                 # 这一句表示"只有直接运行本文件时才执行"，被别人 import 时不执行
    main()                                 # 调用主流程

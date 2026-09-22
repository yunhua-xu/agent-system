# 为什么单独搞一个文件？因为这个文件里【一行 streamlit 都没有】
# 好处：不用启动网页也能用普通 python 跑测试（本机实测就是这么验的）
# ui.py 负责"显示"，这个文件负责"整理"，分工清楚

# ========== 下面 5 个是"小工具函数"，先看懂它们，再看最后的大函数 ==========


def content_to_text(content):
    """把消息里的 content 变成纯文字。content = 内容的意思"""
    # 为什么要这一步？因为不同版本里 content 可能是字符串，也可能是"块"组成的列表
    if isinstance(content, str):        # isinstance = is instance of，"是不是某种类型"的意思
        return content                  # 本来就是字符串，直接用
    if isinstance(content, list):       # 如果是列表（一块一块的）
        parts = []                      # parts = 部分的复数，装每块文字
        for block in content:           # block = 块的意思，自己起的循环变量名
            if isinstance(block, str):          # 这一块本身就是字符串
                parts.append(block)             # append = 追加到列表末尾
            elif isinstance(block, dict):       # 这一块是字典
                # 字典里可能叫 "text"，也可能叫 "content"，取到哪个用哪个
                parts.append(str(block.get("text") or block.get("content") or block))
            else:                               # 其它情况
                parts.append(str(block))        # 直接转成文字
        return "\n".join(parts)         # join = 连接的意思，用换行把它们连成一整段
    return str(content)                 # 兜底：其它类型直接转文字


def short_text(text, limit=40):
    """把长文字截短，方便放进折叠框的标题里。limit = 限制的意思"""
    text = str(text).replace("\n", " ")       # replace = 替换，把换行换成空格，标题里不该有换行
    if len(text) <= limit:                    # len = length 的缩写，长度
        return text                           # 够短就直接返回
    return text[:limit] + "..."                # 太长就切前 limit 个字再加省略号


def format_args(args):
    """把参数（一个字典）变成好读的文字，比如 (参数: a=1, b=2)；args = arguments 的缩写"""
    if not args:                       # 空字典 / None 都算"没有参数"
        return "(无参数)"               # 没有参数就写"无参数"
    if isinstance(args, dict):         # 字典的情况（最常见）
        pairs = []                     # pairs = 一对一对的键值对
        for key, value in args.items():     # items() = 把字典拆成 键,值 一对一对
            pairs.append(f"{key}={value}")   # f"..." 能把变量塞进字符串
        return "(参数: " + ", ".join(pairs) + ")"    # 拼成 (参数: a=1, b=2)
    return f"(参数: {args})"            # 不是字典就整个转文字


def count_tool_calls(messages):
    """★统计这轮一共调了几次工具。messages = 消息列表"""
    # ★★ 本机实测的血泪警示：判断"这轮调没调工具"千万不要用 messages[-1]！
    # 因为 Agent 最后那条 AIMessage（生成回答的那条）的 tool_calls 是空列表 []，
    # 用 messages[-1] 判断永远是"没调工具"，Day52 评测正确率就会恒为 1/3。
    # 正确做法：遍历【所有】message，把每条的 tool_calls 长度累加起来。
    total = 0                                   # 计数器，从 0 开始
    for message in messages:                    # 一条一条看过去
        calls = getattr(message, "tool_calls", None) or []   # getattr = 取属性；取不到就当空列表
        total = total + len(calls)              # 累加这一条里的工具调用个数
    return total                                # 返回总数


def collect_tool_names(messages):
    """★统计这轮用到了哪些工具（去掉重复，保持第一次出现的顺序）"""
    # 同样必须遍历所有 message，理由同上
    names = []                                  # 装工具名，按出现顺序
    for message in messages:                    # 遍历
        calls = getattr(message, "tool_calls", None) or []   # 取出这条的工具调用
        for call in calls:                      # 每个调用里都有工具名
            if isinstance(call, dict):          # 是字典就取 "name" 键
                name = call.get("name")
            else:                               # 是对象就取 .name 属性
                name = getattr(call, "name", None)
            if name and name not in names:      # 有名字、而且还没记过
                names.append(name)              # 加进去
    return names                                # 返回工具名列表


def get_final_answer(messages):
    """取出 Agent 最终给用户的回答文字（最后一条不调工具的 AI 消息）"""
    for message in reversed(messages):           # reversed = 倒过来，从最后一条往前找
        calls = getattr(message, "tool_calls", None) or []      # 这条有没有要调工具
        text = content_to_text(getattr(message, "content", "")) # 这条的文字内容
        if calls:                                # 还在调工具，不是最终回答
            continue                             # continue = 跳过这一条，看下一条
        if text.strip() and "AIMessage" in type(message).__name__:   # 有文字 + 是 AI 消息
            return text                          # strip() = 去掉首尾空白；找到就返回
    return "（没有拿到回答）"                      # 一条都没找到时的兜底文字


# ========== 下面这个才是主角：把 messages 整理成"思考链" ==========


def build_thought_chain(messages):
    """
    ★核心函数：把 Agent 返回的 messages 整理成"一步一步"的思考链
    messages = 消息列表（Agent 跑完回来的那一串）
    返回一个列表，每个元素是一个字典，长这样：
      {
        "step":  第几步（用户提问那步是 0，Agent 的步骤从 1 开始编号）,
        "kind":  类型（human / ai_tool / tool / ai_answer），ui.py 靠它决定颜色,
        "label": 中文短标签（提问 / 调工具 / 工具结果 / 回答）,
        "title": 折叠框的标题（第1步：调用工具 get_time(无参数)）,
        "body":  折叠框展开后放的原始内容
      }
    """
    chain = []            # chain = 链条，装整理好的每一步
    step = 0              # 步数计数器，用户提问记 0，Agent 的动作从 1 开始
    id_to_name = {}       # 工具调用 id -> 工具名 的对照表（ToolMessage 只带 id，靠它还原名字）

    for message in messages:                     # 一条消息一条消息地处理
        kind_name = type(message).__name__       # 取类名，比如 "AIMessage"、"ToolMessage"
        calls = getattr(message, "tool_calls", None) or []      # 这条消息里的工具调用
        text = content_to_text(getattr(message, "content", "")) # 这条消息的文字内容

        # ---------- 第一种：用户提问 ----------
        if kind_name == "HumanMessage":
            chain.append({
                "step": 0,                                            # 0 = 用户提问
                "kind": "human",                                      # 类型：人
                "label": "提问",                                       # 中文标签
                "title": "你的提问：" + short_text(text, 30),           # 折叠框标题
                "body": text,                                         # 展开后的原始内容
            })
            continue                                                  # 这条处理完了，下一条

        step = step + 1                                               # Agent 的动作，步数 +1

        # ---------- 第二种：AI 决定调工具 ----------
        if calls:                                                     # 有工具调用，说明模型想干活
            pieces = []                                               # pieces = 片段，装每个工具的说明
            for call in calls:                                        # 一次可能调好几个工具
                if isinstance(call, dict):                            # 字典形式
                    name = call.get("name")                           # 工具名
                    args = call.get("args")                           # 参数
                    call_id = call.get("id")                          # 这通调用的身份证号
                else:                                                 # 对象形式
                    name = getattr(call, "name", "?")
                    args = getattr(call, "args", {})
                    call_id = getattr(call, "id", None)
                if call_id:                                           # 有身份证号就登记一下
                    id_to_name[call_id] = name                        # 后面 ToolMessage 靠它找名字
                pieces.append(f"{name}{format_args(args)}")           # 拼成 get_time(无参数) 这种
            title = "第" + str(step) + "步：调用工具 " + " + ".join(pieces)   # 例：第1步：调用工具 get_time(无参数)
            chain.append({
                "step": step,
                "kind": "ai_tool",                                    # 类型：AI 调工具
                "label": "调工具",
                "title": title,
                "body": "AI 想调的工具：" + " + ".join(pieces) + "\n\n（这条 AI 消息的正文是空的，因为它只想调工具，还没生成回答）",
            })
            continue                                                  # 下一条

        # ---------- 第三种：工具返回结果 ----------
        if kind_name == "ToolMessage":
            name = getattr(message, "name", None)                     # 消息上直接带了工具名
            if not name:                                              # 万一没带
                name = id_to_name.get(getattr(message, "tool_call_id", None), "未知工具")   # 用身份证号去对照表里查
            chain.append({
                "step": step,
                "kind": "tool",                                       # 类型：工具结果
                "label": "工具结果",
                "title": "第" + str(step) + "步：拿到结果 " + str(name) + " -> " + short_text(text, 30),
                "body": "工具 " + str(name) + " 返回的原始结果：\n\n" + text,
            })
            continue                                                  # 下一条

        # ---------- 第四种：AI 生成最终回答 ----------
        chain.append({
            "step": step,
            "kind": "ai_answer",                                      # 类型：AI 最终回答
            "label": "回答",
            "title": "第" + str(step) + "步：生成回答",
            "body": text,                                             # 展开后是回答全文
        })

    return chain            # 把整理好的链条返回给 ui.py

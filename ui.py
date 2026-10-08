# 作用：把 Agent 跑出来的"思考链"画成网页，让你看见它每一步在想什么、调了什么工具
#
# ★ 本文件依赖两个文件，必须放在【同一个文件夹】里：
#   1) agent_graph.py  —— Day45 写的那个，里面有编译好的 app
#   2) tools.py        —— Day43 写的那个，里面有工具注册表 TOOLS
# ★ 另外本文件还用了同文件夹的 thought_chain.py（纯逻辑，负责把消息整理成一条一条）

import streamlit as st                 # streamlit = 做网页界面的库，简称 st；★本文件所有 st.xxx 都是它的功能
from thought_chain import (            # 从我们自己写的 thought_chain.py 里导入几个函数
    build_thought_chain,               # 把 messages 整理成"一步一步"的思考链
    count_tool_calls,                  # 数这轮调了几次工具
    collect_tool_names,                # 收集这轮用了哪些工具
    get_final_answer,                  # 取 Agent 最终的回答文字
)

# ---------------------------------------------------------------------------
# 第一步：把 Agent 和工具表导进来
# ---------------------------------------------------------------------------
# 这里用 try / except（试着做，出错就接住）是为了给你一个中文提示，
# 而不是甩一大篇看不懂的英文报错
try:
    from agent_graph import app as agent_app       # app = Day45 编译好的 Agent 图；as = 起个别名
    AGENT_ERROR = ""                               # 没出错，错误信息留空
except Exception as e:                             # e = error 的缩写，装错误原因
    agent_app = None                               # 拿不到 Agent 就设为空
    AGENT_ERROR = str(e)                           # 把错误原因存成文字，稍后显示给用户

try:
    from agent_graph import TOOLS                  # ★修：必须和上面 Agent 用同一份清单，否则侧边栏显示的和实际能调的会对不上
    # ★ 2026-10-07 补最关键的一句：agent_graph.py 里的 TOOLS 现在【本身就是从 tools.py 导入的】，
    #   而且 api.py（8000 端口）导入的也是同一个列表 —— 全项目只有一份清单了。
    #   所以这一行从 agent_graph 拿，和直接从 tools 拿，结果完全一样，怎么写都对。
    # ★ 真踩过的坑（两个，2026-09-27 一起修掉）：
    #   坑1【导入源错了】：原来写的是 from tools import TOOLS，
    #     但页面真正调用的是 agent_graph.app，它绑的是 agent_graph.py 自己的 TOOLS。
    #     两份清单内容不一样 —— 侧边栏显示"有联网搜索、有读文件"，可网页根本调不了这两个；
    #     网页明明能调 add（加法）和 query_package（查快递），侧边栏里反而看不到。
    #     所以改成和 Agent 同一个来源 agent_graph，两边永远一致。
    #     （2026-10-07 更进一步：干脆把两份清单合并成一份，从根上断掉这个坑，见 tools.py 末尾那段。）
    #   坑2【取名字的写法错了】：@tool 装饰出来的工具对象【没有 __name__】，只有 .name。
    #     原来写 getattr(t, "__name__", str(t)) 会退到 str(t)，
    #     在侧边栏里塞进一行 194 个字符的垃圾。所以要 .name 优先、__name__ 兜底。
    #     （2026-10-07 注：合并后清单里装的是 tools.py 的【普通函数】，
    #       普通函数反过来 —— 有 __name__、没有 .name，所以正好走到下面 __name__ 那一档，照样对。）
    #   另外 TOOLS 是【列表】不是字典，不能写 TOOLS.keys()
    #   （会报 AttributeError: 'list' object has no attribute 'keys'，
    #     而且这个错会被下面的 except 默默吞掉，侧边栏就永远显示"工具列表为空"，很难发现）。
    if isinstance(TOOLS, dict):                # 万一以后换成了字典形式
        TOOL_NAMES = list(TOOLS.keys())        # keys() = 取出所有名字；list() = 变成列表
    else:                                      # 现在是列表形式（本项目就是这种）
        TOOL_NAMES = [getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in TOOLS]
        # .name 优先（@tool 对象有它）→ __name__ 兜底（普通函数有它）→ 都没有才 str(t)
except Exception:                                  # 万一 agent_graph 也没拿到
    TOOLS = {}                                     # 空字典
    TOOL_NAMES = []                                # 空列表

# ---------------------------------------------------------------------------
# 第二步：页面设置（st.set_page_config 必须是第一个 st 命令，放最前面）
# ---------------------------------------------------------------------------
st.set_page_config(                                # set_page_config = 设置页面配置
    page_title="AI Agent 思考链演示",               # 浏览器标签页上显示的标题
    layout="wide",                                 # 宽屏布局，内容铺满整页
)

st.title("AI Agent 思考链演示")                     # title = 一级大标题
st.caption("看得到 Agent 每一步在想什么、调了什么工具 —— 这就是「思考链」(Chain of Thought)")   # caption = 小号灰色说明文字

# 如果 agent_graph.py 没导进来，就显示错误提示并停下，不要往下跑
if agent_app is None:                              # Agent 没准备好
    st.error("没能导入 agent_graph.py，请确认它和 ui.py 在同一个文件夹。")   # error = 红色错误框
    st.code("原始错误：" + AGENT_ERROR)             # code = 代码样式（等宽字体）显示原始报错
    st.stop()                                      # stop = 停止，后面的代码不再执行

# ---------------------------------------------------------------------------
# 第三步：准备"记忆本" —— st.session_state 是跨次刷新保存数据的地方
# ---------------------------------------------------------------------------
# 为什么要用 session_state？因为 Streamlit 有个特点：
# 你每点一下按钮、每发一条消息，整个脚本会从头到尾重新跑一遍。
# 普通变量会被清空，只有放在 st.session_state 里的东西能活下来。
if "turns" not in st.session_state:                # 第一次打开网页时，"turns"还不存在
    st.session_state.turns = []                    # turns = 回合，每一轮问答算一个回合，先建成空列表

# ---------------------------------------------------------------------------
# 第四步：先在页面上占一块位置，待会儿把对话画进去
# ---------------------------------------------------------------------------
# ★ 顺序很重要：Streamlit 是"脚本从上往下跑，跑到哪就画到哪"。
#   先把这块地方占住（chat_area），等下面输入处理完了，再回来把它填满，
#   这样侧边栏的"历史轮数"才能立刻显示对，不会慢一拍。
chat_area = st.container()                         # container = 容器，一块可以稍后再放东西的区域

# ---------------------------------------------------------------------------
# 第五步：底部输入框 + 调用 Agent
# ---------------------------------------------------------------------------
question = st.chat_input("在这里输入你的问题，比如：现在几点？再算一下 2+3*4")   # chat_input = 底部输入框，按回车提交；Streamlit 会自动把它钉在页面最下面

if question:                                       # 用户真的输入了内容才往下走
    with st.spinner("思考中..."):                   # spinner = 转圈圈的加载提示，Agent 跑的时候显示
        result = agent_app.invoke({                # invoke = 调用 Agent；把问题交给它
            "messages": [{"role": "user", "content": question}]   # 消息格式：角色是 user，内容是问题
        })
    messages = result["messages"]                  # 把 Agent 这一轮产生的所有消息取出来
    answer = get_final_answer(messages)            # 取出最终回答的文字
    chain = build_thought_chain(messages)          # ★把消息整理成思考链

    # 先把这一轮存进"记忆本"，再往下画。这样侧边栏的轮数当场就是对的
    st.session_state.turns.append({                # append = 往列表末尾追加
        "question": question,                      # 这轮的问题
        "answer": answer,                          # 这轮的回答
        "messages": messages,                      # 原始消息（侧边栏统计工具要用）
        "chain": chain,                            # 整理好的思考链（重画历史要用）
    })

# ---------------------------------------------------------------------------
# 第六步：侧边栏（st.sidebar）—— 控制面板 + 状态显示
# ---------------------------------------------------------------------------
with st.sidebar:                                   # with 的意思：下面缩进的内容都放进侧边栏
    st.header("控制面板")                           # header = 二级标题，比 title 小一号

    # ---- 清空对话按钮 ----
    if st.button("清空对话"):                       # button = 按钮；被点一下返回 True
        st.session_state.turns = []                # 把回合列表清空
        st.rerun()                                 # rerun = 立刻重新跑一遍脚本，让界面刷新

    st.divider()                                   # divider = 一条分隔横线

    # ---- 历史轮数 ----
    st.metric(                                     # metric = 指标卡（大数字那种）
        label="历史轮数",                           # 卡片上面的小字
        value=len(st.session_state.turns),         # 卡片上的大数字 = 一共有几个回合
    )

    st.divider()

    # ---- 可用的工具列表（来自 tools.py）----
    st.subheader("可用的工具")                      # subheader = 三级标题
    if TOOL_NAMES:                                 # 工具表不是空的
        for tool_name in TOOL_NAMES:               # 一个一个列出来
            st.markdown("- `" + tool_name + "`")    # markdown = 支持 Markdown 语法；反引号让它变成代码样式
    else:
        st.caption("（没读到 tools.py，工具列表为空）")

    # ---- 本次会话已经用过的工具（靠遍历所有消息统计出来）----
    used_names = []                                # used_names = 用过的工具名，先空着
    for turn in st.session_state.turns:            # 遍历每一个回合
        for name in collect_tool_names(turn["messages"]):   # 这个回合用到的工具
            if name not in used_names:             # 没记过才记（去重）
                used_names.append(name)            # 记下来
    st.subheader("这次已经用过的工具")
    if used_names:                                 # 有就用绿字列出来
        st.success("、".join(used_names))           # success = 绿色成功框
    else:
        st.caption("还没用过任何工具")

    st.divider()

    # ---- 颜色说明（一眼看懂哪种颜色是谁）----
    with st.expander("三种颜色分别代表什么？"):
        st.info("蓝色 = 你的提问")
        st.warning("黄色 = AI 决定调用工具（这一步只说要调什么，还没回答）")
        st.success("绿色 = 工具真的执行完，返回的结果")
        st.markdown("普通正文 = AI 最终生成的回答")

    # ---- 怎么运行（写在这里，免得你翻代码）----
    with st.expander("怎么运行这个网页？"):
        st.markdown(
            "1. 打开命令行（Git Bash / CMD 都行）\n"
            "2. 切到 ui.py 所在的文件夹\n"
            "3. 敲命令：`streamlit run ui.py`\n"
            "4. 浏览器会自动打开 http://localhost:8501\n"
            "5. 在底部输入框问一句「现在几点？」，然后展开「第1步：调用工具 get_time(无参数)」，"
            "能看见工具名和参数，就算成功。"
        )

# ---------------------------------------------------------------------------
# 第七步：画"思考链"的函数 —— 三种颜色区分三种消息
# ---------------------------------------------------------------------------
def render_thought_chain(chain, expanded):
    """
    把思考链画到网页上。chain = build_thought_chain() 整理好的列表
    expanded = True 表示折叠框默认展开，False 表示默认收起
    颜色约定（这是关键，一眼就能分清谁在说话）：
      提问     -> 蓝色（st.info）
      调工具   -> 黄色（st.warning）
      工具结果 -> 绿色（st.success）
      回答     -> 普通正文（st.markdown）
    """
    for item in chain:                             # 一步一步画过去
        kind = item["kind"]                        # kind = 类型，决定用哪个颜色

        if kind == "human":                        # 用户提问
            icon = ":material/person:"             # 图标：小人（material 图标是纯 ASCII 写法，不会乱码）
            box = st.info                          # info = 蓝色信息框
        elif kind == "ai_tool":                    # AI 决定调工具
            icon = ":material/build:"              # 图标：扳手
            box = st.warning                       # warning = 黄色警告框
        elif kind == "tool":                       # 工具返回结果
            icon = ":material/check_circle:"       # 图标：对勾
            box = st.success                       # success = 绿色成功框
        else:                                      # 剩下的就是 AI 的最终回答
            icon = ":material/smart_toy:"          # 图标：小机器人
            box = st.markdown                      # markdown = 普通正文

        with st.expander(item["title"], icon=icon, expanded=expanded):   # expander = 可折叠框；title 是折叠标题
            box(item["body"])                      # 展开后显示原始内容

# ---------------------------------------------------------------------------
# 第八步：把占好的位置填满 —— 逐轮画出对话和思考链
# ---------------------------------------------------------------------------
with chat_area:                                    # 回到第四步占的位置里画
    if not st.session_state.turns:                 # 一轮都没有
        st.info("还没有对话。在下面的输入框里问一句试试，比如：现在几点？再算一下 2+3*4")

    for turn in st.session_state.turns:            # 一个一个回合画过去
        with st.chat_message("user"):              # chat_message = 聊天气泡；"user" 表示这是用户说的话
            st.markdown(turn["question"])          # 显示这轮的问题

        with st.chat_message("assistant"):         # "assistant" = 助手（也就是我们的 Agent）
            st.markdown(turn["answer"])            # 显示这轮的回答

            # ★ 数调用次数必须遍历所有消息累加（不能用 messages[-1]，原因见 thought_chain.py 的注释）
            total_calls = count_tool_calls(turn["messages"])
            with st.expander("查看这轮的思考链（调工具 " + str(total_calls) + " 次）"):   # 折叠框标题带上次数
                render_thought_chain(turn["chain"], expanded=False)   # 历史回合默认收起，界面才清爽


# ===========================================================================
# 怎么运行 / 看到什么算成功
# ===========================================================================
# 【运行命令】在命令行里，切到 ui.py 所在文件夹，敲：
#     streamlit run ui.py
#   浏览器会自动打开 http://localhost:8501
#
# 【看到什么算成功】
#   1. 页面顶部出现大标题「AI Agent 思考链演示」
#   2. 左侧出现「控制面板」侧边栏，能看到「可用的工具」下面列着 get_time / calculate / get_weather
#   3. 底部有输入框，输入「现在几点？」回车
#   4. 先看到「思考中...」转圈，然后出现回答
#   5. 回答下面出现折叠框，标题类似：
#        第1步：调用工具 get_time(无参数)      <- 黄色
#        第2步：拿到结果 get_time -> 2026-...  <- 绿色
#        第3步：生成回答                        <- 普通正文
#      点开「第1步」，能看到「AI 想调的工具：get_time(无参数)」，就说明思考链跑通了
#   6. 左侧「历史轮数」当场变成 1（不用等下一条消息）
#
# 【常见问题】
#   报 ModuleNotFoundError: No module named 'agent_graph'
#     -> 意思是：找不到 agent_graph.py 这个文件
#     -> 修法：把 Day45 写的 agent_graph.py 和 Day43 写的 tools.py 复制到和 ui.py 同一个文件夹
#   报 Function must have a docstring if description not provided
#     -> 意思是：tools.py 里的工具函数少了三引号说明
#     -> 修法：给每个工具函数下面加一行 """这个工具是干嘛的"""

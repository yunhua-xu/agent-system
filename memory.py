
# -*- coding: utf-8 -*-
"""
memory.py = 记忆模块（Day47：双记忆系统）
=========================================================================
这个文件干两件事：

  1) 短期记忆 ShortTermMemory —— 只保留最近几轮"原文"。
     更早的对话不是扔掉，而是让大模型压成"一段摘要"，拼进 system prompt。
     这样既有细节（最近几轮），又不会把上下文撑爆（早的变摘要）。

  2) 长期记忆 LongTermMemory  —— 把"事实"存进 ChromaDB 向量库。
     换个新会话（对话历史清空）也能把事实查回来，塞进 system prompt。
     这就是"跨对话记得住"的原理：记忆不在对话里，在数据库里。

运行方式（在本文件所在目录）：
    python memory.py
=========================================================================
"""

import os                                  # os = operating system（操作系统）的缩写；固定写法，Python 自带的模块
from dotenv import load_dotenv             # load_dotenv = load（加载）+ env（environment 环境变量）；固定写法，别人写好的库函数
from langchain_openai import ChatOpenAI    # ChatOpenAI = 聊天用的 OpenAI 客户端；固定写法，用 OpenAI 兼容格式去调 DeepSeek
from langchain_core.messages import (      # 这一行是导入"消息类型"，括号里是要导入的几个名字
    SystemMessage,                         # SystemMessage = 系统消息（给 AI 定规矩的那段）；固定写法
    HumanMessage,                          # HumanMessage  = 人类消息（用户说的话）；固定写法
    AIMessage,                             # AIMessage     = AI 消息（AI 回的话）；固定写法
)
import chromadb                            # chromadb = 本地向量数据库；固定写法，装好的第三方库

# -------------------------------------------------------------------------
# 本文件里出现的英文名，先一次性说清（后面注释里就不再重复解释了）
#   llm        = large language model（大语言模型）的缩写，业内习惯这么叫
#   summarize  = 总结、概括           —— 自己起的函数名
#   memory     = 记忆                 —— 自己起的类名一部分
#   Short/Long = 短 / 长              —— 自己起的类名前缀
#   Term       = 期（短期、长期的那个"期"）—— 自己起的类名一部分
#   prompt     = 提示词（发给模型的那段话）—— 固定说法，不是随便起的
#   base       = 基础的               —— 自己起的变量名
#   history    = 历史                 —— 自己起的变量名
#   summary    = 摘要                 —— 自己起的变量名
#   recall     = 回忆、召回           —— 自己起的函数名
#   fact       = 事实                 —— 自己起的变量名一部分
#   fid        = fact id（事实的编号）—— 自己起的变量名
#   seq        = sequence（序号）     —— 自己起的变量名
# -------------------------------------------------------------------------


# -------------------------------------------------------------------------
# 0. 准备工作：读 key + 建模型
# -------------------------------------------------------------------------

# 读 .env（里面放着 DEEPSEEK_API_KEY）；r"..." 前面的 r = raw（原样），防止反斜杠被当成转义
load_dotenv(r"E:/8月3日Ai学习计划/每日练习/agent_system/.env")   # 固定写法，把 .env 读进环境变量

# llm = large language model 的缩写，就是"大模型客户端"
# temperature=0 表示每次回答尽量稳定（不要随机发挥），做记忆压缩要的是稳定
llm = ChatOpenAI(                                                # 创建一个 DeepSeek 客户端，存到 llm 这个变量里
    model="deepseek-flash",                                      # 模型名，本机只能是这个或 deepseek-v4-pro
    base_url="https://api.deepseek.com",                         # base_url = 接口地址
    api_key=os.getenv("DEEPSEEK_API_KEY"),                       # getenv = 取环境变量的值；不要写死在代码里
    temperature=0,                                               # temperature = 温度；0 = 最稳定不发挥
)                                                                # 括号收尾，这个多行写法是 Python 固定语法


# -------------------------------------------------------------------------
# (a) 短期记忆：最近 N 轮原文 + 更早的压缩摘要
# -------------------------------------------------------------------------

def summarize_messages(llm, messages, old_summary=""):
    """
    summarize = 总结、概括。
    把一串旧消息压成一段摘要文字。

    参数：
      llm         —— 用哪个大模型来压缩（必须当参数传进来！不能凭空用）
      messages    —— 要压缩的旧消息列表（HumanMessage / AIMessage 对象）
      old_summary —— 之前已经压好的旧摘要，会一起并进去（摘要滚雪球）

    返回：一段中文字符串
    """
    # 先把消息对象拼成人类看得懂的对话文字
    lines = []                                          # lines = 行，装每一句对话
    for m in messages:                                  # 一条一条消息看过去
        # isinstance = 判断"这个东西是不是某个类型"
        who = "用户" if isinstance(m, HumanMessage) else "AI"   # 用户说的标"用户"，其余标"AI"
        lines.append(who + ": " + m.content)            # 拼成 "用户: xxxxx"
    dialog_text = "\n".join(lines)                      # 用换行把每一句接起来

    # 拼提示词：让模型只做"压缩"，不要聊天
    prompt = (                                          # prompt = 提示词；括号里几行字符串会自动接成一句
        "请把下面这段对话压缩成一小段摘要，只保留关键事实"    # 第 1 段要求
        "（比如姓名、喜好、目标、约定、说过的重要信息），"     # 第 2 段要求
        "不要评论、不要寒暄，直接输出摘要正文：\n\n"          # 第 3 段要求；\n = 换行
        + dialog_text                                   # 再把上面拼好的对话正文接上
    )                                                   # 括号收尾
    if old_summary:                                     # 如果有旧摘要，先给模型看，让它合并
        prompt = ("这是之前的旧摘要：\n" + old_summary + "\n\n"          # 旧摘要放前面
                  "请把旧摘要和新对话一起合并成一份新摘要：\n\n" + dialog_text)   # 新对话放后面

    resp = llm.invoke(prompt)                           # invoke = 调用，让模型干活
    return resp.content.strip()                         # content = 模型回的文字，strip() = 去掉首尾空白


class ShortTermMemory:
    """
    Short = 短，Term = 期，Memory = 记忆 —— 短期记忆。
    只保留最近 max_rounds 轮原文；更早的自动压缩进 self.summary。
    """

    def __init__(self, llm, max_rounds=3):
        # __init__ = 初始化，创建对象时自动跑一次
        self.llm = llm                      # self = 自己，把传进来的模型存到自己身上
        self.max_rounds = max_rounds        # 最多保留几轮原文（一轮 = 用户一句 + AI 一句）
        self.history = []                   # history = 历史，装最近几轮的消息对象
        self.summary = ""                   # summary = 摘要，装更早内容的压缩结果

    def add_round(self, user_text, ai_text):
        """加一轮对话（用户说一句 + AI 回一句）。"""
        self.history.append(HumanMessage(content=user_text))   # 存用户这句
        self.history.append(AIMessage(content=ai_text))        # 存 AI 这句
        self._maybe_compress()                                 # 加完就检查要不要压缩

    def _maybe_compress(self):
        """_ 开头表示"内部函数"，外面不用直接调用。超长了就把旧的压缩掉。"""
        keep = self.max_rounds * 2                  # 一轮 2 条消息，所以要保留的条数 = 轮数 x 2
        if len(self.history) <= keep:               # 还没超，啥也不干
            return                                  # return 后面不带东西 = 直接结束这个函数
        old = self.history[:-keep]                  # [:-keep] = 除了最后 keep 条，前面那些就是"旧的"
        self.history = self.history[-keep:]         # [-keep:] = 只留最后 keep 条（最近几轮）
        # 把旧消息压成摘要，并接在已有摘要后面
        self.summary = summarize_messages(self.llm, old, self.summary)   # 旧摘要传进去一起合并

    def build_system_prompt(self, base_prompt):
        """
        build = 构建，system prompt = 系统提示。
        把"摘要"拼到原来的系统提示后面，返回一段更长的系统提示。
        """
        if not self.summary:                        # 没有摘要就直接用原来的
            return base_prompt                      # 原样返回基础提示
        return base_prompt + "\n\n【之前对话的摘要】\n" + self.summary   # 基础提示 + 摘要

    def get_messages(self, base_prompt):
        """
        组装成真正要发给大模型的消息列表：
        [system(带摘要)] + [最近几轮的原文]
        """
        msgs = [SystemMessage(content=self.build_system_prompt(base_prompt))]   # 第 1 条永远是系统提示
        msgs.extend(self.history)                   # extend = 把 history 里的消息一条条接上去
        return msgs                                 # 返回组装好的消息列表


# -------------------------------------------------------------------------
# (b) 长期记忆：ChromaDB 存事实
# -------------------------------------------------------------------------

CHROMA_PATH = "./chroma_db"        # 向量库存哪个文件夹（相对当前运行目录；想换地方就改这里）
COLLECTION_NAME = "facts"          # collection = 集合，相当于数据库里的一张表


class LongTermMemory:
    """
    Long = 长，Term = 期 —— 长期记忆。
    存在磁盘上，关掉程序、换个新会话，数据还在。
    """

    def __init__(self, path=CHROMA_PATH, collection_name=COLLECTION_NAME):
        # PersistentClient = 持久化客户端，数据会写到磁盘，不是用完就没
        self.client = chromadb.PersistentClient(path=path)
        # get_or_create_collection = 有这个集合就取出来，没有就新建一个
        self.col = self.client.get_or_create_collection(collection_name)
        # count() = 数一数现在库里已经存了几条事实，用来接着编号
        # 为什么要接着编号：id 是主键，同一个 id 再 add 一次会把旧的【覆盖】掉（upsert 行为）
        self._seq = self.col.count()

    def add_fact(self, text):
        """add = 添加，fact = 事实。存一条事实进向量库，返回它的 id。"""
        self._seq += 1                              # 编号 +1
        fid = "fact_" + str(self._seq)              # 拼出唯一 id，比如 fact_1、fact_2
        # ids 必须唯一！如果写死成 "fact_1"，第二次存就会把第一条覆盖掉
        self.col.add(ids=[fid], documents=[text])   # documents = 文档，就是要存的那句话
        return fid                                  # 把 id 返回去，方便打印看

    def recall(self, query, n=3):
        """
        recall = 回忆、召回。拿一句话去库里找最像的 n 条事实，返回文字列表。
        """
        count = self.col.count()                    # 先看库里总共几条
        if count == 0:                              # 空库直接返回空列表，不然查询会报错
            return []                               # 返回一个空列表
        n = min(n, count)                           # min = 取两者里小的那个；n 不能超过总数，否则报错
        # query_texts = 直接给文字，让 chroma 用它自己的默认模型去算向量（本机实测可用，384 维）
        result = self.col.query(query_texts=[query], n_results=n)   # query = 查询，去库里找最像的
        return result["documents"][0]               # documents[0] = 第一条查询的结果列表


# -------------------------------------------------------------------------
# (c) 把长期记忆拼进 system prompt
# -------------------------------------------------------------------------

def build_system_prompt(base_prompt, facts):
    """
    base_prompt = 原来的系统提示，facts = 查回来的事实列表。
    把事实一条条列成 "- xxx"，贴到系统提示后面。
    """
    if not facts:                                   # 没查到东西就原样返回
        return base_prompt                          # 返回原来的系统提示
    lines = []                                      # 准备装每一条事实
    for f in facts:                                 # 一条条遍历
        lines.append("- " + f)                      # 前面加个短横线，看起来像清单
    return base_prompt + "\n\n【关于用户的长期记忆】\n" + "\n".join(lines)   # join = 用换行把清单接成一块


def chat(llm, system_prompt, history=None):
    """
    小工具：发一次对话，返回 AI 的文字回答。
    system_prompt = 系统提示，history = 之前的消息列表（可选）。
    """
    msgs = [SystemMessage(content=system_prompt)]   # 第 1 条永远是系统提示
    if history:                                     # 如果有历史消息
        msgs.extend(history)                        # extend = 把历史一条条接到 msgs 后面
    resp = llm.invoke(msgs)                         # resp = response（回复）的缩写；invoke = 调用模型
    return resp.content                             # content = 模型回的文字，取出来返回


# -------------------------------------------------------------------------
# (d) 演示：跨对话能不能记住
# -------------------------------------------------------------------------

if __name__ == "__main__":          # 只有直接运行本文件时才执行，被 import 时不执行
    # 先建好长期记忆（它会打开/新建 ./chroma_db 这个文件夹）
    mem = LongTermMemory()

    # ============ 第 1 个会话：用户自我介绍 ============
    print("=" * 60)                                        # 打印一排等号当分隔线，好看而已
    print("第 1 个会话")                                     # 打印小标题
    print("=" * 60)                                        # 再打一排等号

    base = "你是一个聊天助手，回答要简短。"                  # base = 基础的系统提示，后面所有会话共用
    # 新建一个短期记忆对象（只属于这个会话）
    stm1 = ShortTermMemory(llm, max_rounds=3)              # stm = ShortTermMemory 的简写，自己起的变量名

    user_say = "我叫小明，喜欢打篮球。"                       # 用户说的第一句
    print("用户:", user_say)                                # 把用户说的话打出来
    # chat() 是我们上面写的小工具；这里只发 [系统提示 + 用户这一句]，没有别的历史
    ai_say = chat(llm, stm1.build_system_prompt(base), [HumanMessage(content=user_say)])
    print("AI  :", ai_say)                                  # AI 回答
    stm1.add_round(user_say, ai_say)                        # 把这一轮存进短期记忆

    # 把用户这句话里的事实存进长期记忆
    # 这里为了直观，直接把两个事实拆开存（真实项目里可以让模型帮你抽取）
    fid1 = mem.add_fact("用户的名字叫小明")                   # fid = fact id，存第 1 条，拿到编号
    fid2 = mem.add_fact("用户喜欢打篮球")                     # 存第 2 条，拿到编号
    print("[长期记忆] 已存:", fid1, "->", "用户的名字叫小明")   # 打印存进去的编号和内容
    print("[长期记忆] 已存:", fid2, "->", "用户喜欢打篮球")     # 同上
    print("[长期记忆] 当前库里共", mem.col.count(), "条")       # count() = 数一数库里现在几条

    # ============ 第 2 个会话：全新对话，问它记不记得 ============
    print()                                                 # 打印一个空行，隔开两段输出
    print("=" * 60)                                         # 分隔线
    print("第 2 个会话（全新，没有任何对话历史）")              # 小标题
    print("=" * 60)                                         # 分隔线

    question = "我叫什么？喜欢什么？"                          # 新会话里的问题
    print("用户:", question)                                  # 打印问题

    # 关键一步：先拿问题去长期记忆里查
    facts = mem.recall(question, n=3)                       # recall = 回忆；拿问题去向量库找最像的 3 条
    print("[长期记忆] 查到:", facts)                           # 打印查到了啥

    # 把查到的事实拼进系统提示
    sys2 = build_system_prompt(base, facts)                 # sys = system prompt 的简写，自己起的名

    # 新会话 = 空的 history，什么都不带，只靠系统提示里的长期记忆
    answer = chat(llm, sys2, [HumanMessage(content=question)])   # 只发 [系统提示 + 这一句问题]
    print("AI  :", answer)                                   # 打印 AI 的回答

    # ============ 短期记忆压缩演示 ============
    print()                                                 # 空行
    print("=" * 60)                                         # 分隔线
    print("短期记忆压缩演示（max_rounds=2，聊 4 轮看摘要）")     # 小标题
    print("=" * 60)                                         # 分隔线

    stm2 = ShortTermMemory(llm, max_rounds=2)               # 这个只留最近 2 轮原文，好触发压缩
    fake_dialog = [                                         # fake = 假的；假装聊了 4 轮的对话，自己起的名
        ("我最近在学 Python。", "好的，加油。"),               # 第 1 轮：(用户说的, AI 回的)
        ("我打算两个月后找 AI 相关工作。", "目标很明确。"),       # 第 2 轮
        ("我白天要上班，只能晚上学。", "时间安排得不错。"),        # 第 3 轮
        ("我住在杭州。", "杭州挺好的。"),                       # 第 4 轮
    ]
    for q, a in fake_dialog:                                # 一轮一轮丢进去
        stm2.add_round(q, a)                                # 每加一轮，内部会自动检查要不要压缩

    print("[短期记忆] 保留的原文条数:", len(stm2.history))      # len = length（长度）；应该只剩 4 条（2 轮 x 2 句）
    print("[短期记忆] 压缩出的摘要:", stm2.summary)             # 前面 2 轮已经被压成这一段摘要了
    print("[短期记忆] 最终 system prompt:")                    # 打印最终拼出来的系统提示
    print(stm2.build_system_prompt("你是一个聊天助手。"))        # 摘要贴在基础提示后面

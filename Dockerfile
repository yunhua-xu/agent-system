# Dockerfile —— 把整个 Agent 系统"打包成一台可以搬走的机器"
# 文件名固定就叫 Dockerfile（一个字都不能改，Docker 只认这个名字）
# 用法：docker build -t agent-system:1.0 .        （在项目目录下执行）
# ============================================================


# FROM = 从哪个"基础镜像"开始（镜像=装好系统的光盘模板；容器=拿它跑起来的那台机器）
# python:3.10-slim = 官方 Python 3.10 精简版，自带 pip，体积小（约 120MB）
# 为什么不用 latest？因为 latest 会随时间变，今天能构建、下个月可能就构建失败，版本要写死
FROM python:3.10-slim


# WORKDIR = 工作目录（working directory 的缩写）。进入容器后默认站在哪个文件夹
# 相当于在容器里执行了一次 cd /app；后面的 COPY、RUN、CMD 都相对于这个目录
WORKDIR /app


# ENV = 环境变量（environment 的缩写），设一次后面所有命令都生效
# PYTHONUNBUFFERED=1 = Python 输出不缓存，实时打印日志（否则 docker logs 看不到实时输出）
# PYTHONIOENCODING=utf-8 = 让 Python 的输入输出统一用 utf-8 编码
#   —— 这条是给我们本机踩过的坑准备的：本机 GBK 环境 print emoji 会直接 UnicodeEncodeError
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8


# ★★ 面试必问：为什么先 COPY requirements.txt，而不是直接 COPY . ？ ★★
# Docker 构建是一层一层（layer）来的，每一层只要内容没变就会用缓存，不重新执行。
# 依赖清单（requirements.txt）很少改，源代码（.py）天天改。
# 先拷 requirements.txt 再 pip install，就把"装依赖"这层单独锁成一层：
#   → 以后你只改 .py 文件，这层缓存直接命中，构建只要几秒；
#   → 如果反过来先 COPY . 再装依赖，改一个字就会让缓存失效，每次都要重装全部依赖（几分钟）。
# 一句话记住：把"变得慢的东西"放前面，"变得快的东西"放后面。
COPY requirements.txt .


# RUN = 构建镜像时执行的命令（在容器里跑一条命令）
# pip install -r requirements.txt = 按清单装依赖（-r = read 读取清单文件）
# --no-cache-dir = 不保留 pip 下载缓存，镜像能小几百 MB
# -i https://pypi.tuna.tsinghua.edu.cn/simple = 换清华镜像源，国内装包快很多（不换会超时）
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple


# COPY . . = 把当前目录（宿主机项目目录）的剩余文件全部拷进容器的 /app
#   第一个点 = 宿主机当前目录（构建时所在目录）
#   第二个点 = 容器里的 WORKDIR（也就是 /app）
# 注意：被 .dockerignore 里列出的文件（.env、__pycache__ 等）不会被拷进来
COPY . .


# EXPOSE = 声明这个容器打算对外用哪些端口（只是"说明书"，真正映射靠 docker run -p / compose ports）
# 8000 = FastAPI 接口（api.py）
# 8501 = Streamlit 网页（ui.py）
# 这个镜像两个服务共用，所以两个端口都声明上
EXPOSE 8000 8501


# CMD = 容器启动时默认执行的命令（一个 Dockerfile 只有最后一条 CMD 生效）
# 中括号这种写法叫 exec 格式（推荐），它不经过 shell，能被正确接收停止信号
# "uvicorn" = 启动 FastAPI 的服务器程序；"api:app" = api.py 文件里的 app 这个变量
# --host 0.0.0.0 = 监听所有网卡，容器外（也就是你的浏览器）才连得进来；写 127.0.0.1 就只有容器自己能用
# --port 8000 = 监听 8000 端口
# 注意：docker-compose.yml 里的 ui 服务会用 command 覆盖掉这条 CMD，改成启动 Streamlit
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

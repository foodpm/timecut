 # ============================================
 # TimeCut - 后端应用 Docker 镜像
 # ============================================
 FROM python:3.12-slim
 
 WORKDIR /app
 
 # 安装系统依赖：FFmpeg + 编译工具
 RUN apt-get update && apt-get install -y --no-install-recommends \
     ffmpeg \
     && rm -rf /var/lib/apt/lists/*
 
 # 安装 Python 依赖
 COPY app/requirements.txt .
 RUN pip install --no-cache-dir -r requirements.txt
 
 # 复制应用代码
 COPY app/ .
 
 # 暴露端口
 EXPOSE 8090
 
 # 数据卷挂载点
 VOLUME ["/data"]
 
 # 启动
 CMD ["python", "main.py"]

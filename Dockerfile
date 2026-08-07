 # ============================================
 # TimeCut - 后端应用 Docker 镜像
 # ============================================
 FROM python:3.12-slim
 
 WORKDIR /app
 
 # 安装系统依赖：FFmpeg + curl（构建时下载模型用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 下载 YOLO11n 人物检测模型（官方导出 ONNX，随镜像分发，NAS 离线可用）
RUN mkdir -p /app/models \
    && curl -fsSL -o /app/models/yolo11n.onnx \
       https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx \
    && ls -lh /app/models/
 
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

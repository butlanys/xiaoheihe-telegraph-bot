FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY xiaoheihe.py main.py ./

# 运行
CMD ["python3", "main.py"]

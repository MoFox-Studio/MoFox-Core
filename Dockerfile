FROM python:3.13.5-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 安装编译器、git 和 Python 开发头文件
RUN apt-get update && apt-get install -y build-essential git python3-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# 同时声明两个端口
EXPOSE 8000
EXPOSE 12138

CMD ["uv", "run", "bot.py"]

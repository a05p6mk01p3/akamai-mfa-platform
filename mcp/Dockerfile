FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system mcp && \
    useradd --system --gid mcp --home-dir /app --shell /usr/sbin/nologin mcp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
RUN chown -R mcp:mcp /app
USER mcp
EXPOSE 9000
CMD ["python", "-m", "app.server"]

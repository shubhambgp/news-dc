# One image for dev and prod. The build stage installs deps with uv; the runtime stage carries
# only the venv and the code (no uv, no build cache), runs as a non-root user.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
# venv lives outside /app so the dev bind mount of ./backend doesn't hide it
ENV PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY . .
RUN useradd --create-home --uid 10001 app && mkdir /models && chown app /models  # fastembed cache volume
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE run_streamlit.py ./
COPY .env.example ./.env.example
COPY src ./src
COPY scripts ./scripts
COPY assets ./assets
COPY tests ./tests
COPY playwright ./playwright

RUN pip install --upgrade pip \
    && pip install -e .

EXPOSE 8501

CMD [
  "streamlit",
  "run",
  "src/luxnews/streamlit_app.py",
  "--server.address=0.0.0.0",
  "--server.port=8501",
  "--server.headless=true"
]

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# editable install keeps the package under /app, so PROJECT_ROOT (data/, .env) resolves to /app
RUN pip install --upgrade pip && pip install -e .

COPY app ./app
COPY .streamlit ./.streamlit

RUN useradd --create-home adpulse && mkdir -p /app/data && chown -R adpulse /app
ENV DATA_DIR=/app/data
USER adpulse

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]

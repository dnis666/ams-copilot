FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY data ./data
COPY evals ./evals

RUN useradd --create-home --uid 10001 app && mkdir -p /app/var && chown -R app /app/var
USER app

EXPOSE 8000
CMD ["uvicorn", "ams_copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]

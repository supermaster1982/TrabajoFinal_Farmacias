FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.8.3 \
    && poetry config virtualenvs.create false

COPY pyproject.toml ./
RUN poetry install --no-root --without dev

COPY src/ ./src/
COPY data/ ./data/

ENV PYTHONPATH=/app/src
EXPOSE 8080

CMD ["uvicorn", "asistente_farmacias.api.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.14-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.14-slim

RUN groupadd -r radarsolar && useradd -r -g radarsolar radarsolar

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ src/
COPY data/ data/
COPY .env .env

RUN chown -R radarsolar:radarsolar /app

USER radarsolar

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8080

EXPOSE 8080

CMD ["python", "-X", "utf8", "src/main.py"]

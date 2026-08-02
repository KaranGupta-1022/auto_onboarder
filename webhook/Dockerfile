# wedhook/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY webhook.py /app/webhook.py

RUN pip install --no-cache-dir uvicorn fastapi

EXPOSE 443
CMD ["uvicorn", "webhook:app", "--host", "0.0.0.0", "--port", "443", "--ssl-keyfile", "/tls/tls.key", "--ssl-certfile", "/tls/tls.crt"]
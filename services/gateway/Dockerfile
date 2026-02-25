FROM python:3.11-slim

WORKDIR /app

COPY shared /opt/shared
RUN pip install --no-cache-dir /opt/shared

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

COPY services/gateway/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]

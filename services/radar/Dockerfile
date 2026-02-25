FROM python:3.11-slim

WORKDIR /app

# Install shared package first
COPY shared /opt/shared
RUN pip install --no-cache-dir /opt/shared

# Install service dependencies
COPY services/radar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy service code
COPY services/radar/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

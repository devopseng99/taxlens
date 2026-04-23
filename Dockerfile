FROM docker.io/python:3.11-slim

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY scripts/ /app/scripts/

# Storage mount point
RUN mkdir -p /data/documents
VOLUME /data/documents

ENV TAXLENS_STORAGE_ROOT=/data/documents
ENV TAXLENS_MAX_FILE_MB=30

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--log-level", "warning"]

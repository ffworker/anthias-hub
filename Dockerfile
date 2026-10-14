FROM python:3.12-slim
WORKDIR /opt/hub
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY wsgi.py .
RUN mkdir -p /data /config && chown 10001:10001 /data /config
USER 10001:10001
EXPOSE 8765
CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "1", "--threads", "4", "--timeout", "360", "wsgi:app"]

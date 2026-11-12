FROM python:3.12-slim
WORKDIR /opt/hub
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TMPDIR=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY wsgi.py .
# GitHub Actions passes the immutable main commit, rather than relying on the
# host's .env tag, which can differ from the currently running container.
ARG HUB_BUILD_SHA=dev
RUN printf '%s\n' "$HUB_BUILD_SHA" > /opt/hub/.build-revision
LABEL org.opencontainers.image.revision="$HUB_BUILD_SHA"
RUN mkdir -p /data /config && chown 10001:10001 /data /config
USER 10001:10001
EXPOSE 8765
CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "1", "--threads", "4", "--timeout", "7200", "wsgi:app"]

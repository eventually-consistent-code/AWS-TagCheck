FROM python:3.12-slim

WORKDIR /app

# Install with the storage extra so every backend (S3 + Azure Blob + GCS)
# works in the web app out of the box.
COPY pyproject.toml README.md ./
COPY tagmanager/ tagmanager/
COPY aws.py aws_tag_manager.py canonical.json ./
RUN pip install --no-cache-dir ".[storage]"

# Persistent tree for generated artifacts (and dev sqlite), owned by an
# unprivileged runtime user. TAGMANAGER_ARTIFACT_DIR points the web app's
# artifact writer here; mount /data as a volume to keep them across
# restarts.
RUN useradd --create-home --uid 10001 tagmanager \
    && mkdir -p /data/artifacts \
    && chown -R tagmanager:tagmanager /data
ENV TAGMANAGER_ARTIFACT_DIR=/data/artifacts
VOLUME ["/data"]

USER tagmanager

EXPOSE 8080

# Liveness via the app's own health endpoint — stdlib urllib, no curl in
# the slim image.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/api/health', timeout=4).status==200 else 1)"]

CMD ["tagmanager-serve"]

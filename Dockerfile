FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY tagmanager/ tagmanager/
COPY aws.py aws_tag_manager.py canonical.json ./
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["tagmanager-serve"]

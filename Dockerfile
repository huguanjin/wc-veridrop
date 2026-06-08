FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VERIDROP_IMAGE_CACHE_DIR=/opt/veridrop/web_data/images \
    VERIDROP_MONGODB_CONFIG=/opt/veridrop/mongodb_config.yaml \
    VERIDROP_WISHLIST_PATH=/opt/veridrop/web_data/wishlist.txt

WORKDIR /opt/veridrop

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY mongodb_config.example.yaml ./mongodb_config.yaml
COPY src ./src
COPY web ./web
COPY data ./data

RUN python -m pip install --upgrade pip \
    && pip install -e ".[web]" \
    && mkdir -p /opt/veridrop/web_data/images \
    && useradd --create-home --shell /usr/sbin/nologin veridrop \
    && chown -R veridrop:veridrop /opt/veridrop

USER veridrop

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]

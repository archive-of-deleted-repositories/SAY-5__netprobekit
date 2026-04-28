# syntax=docker/dockerfile:1.7
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
RUN make -C target

FROM python:3.12-slim
WORKDIR /srv
COPY --from=build /src/target/target /usr/local/bin/target
COPY netprobe ./netprobe
COPY tests ./tests
COPY pyproject.toml ./
COPY web ./web
RUN pip install --no-cache-dir ".[dev]"
RUN useradd -u 10001 -m np && chown -R np /srv
USER np
ENV PATH=/usr/local/bin:$PATH
CMD ["python", "-m", "netprobe.runner", "/usr/local/bin/target"]

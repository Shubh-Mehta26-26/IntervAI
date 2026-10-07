FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ openjdk-17-jdk-headless libseccomp-dev && rm -rf /var/lib/apt/lists/*
COPY sandbox/guard.c /tmp/guard.c
RUN gcc -O2 -Wall -Wextra /tmp/guard.c -lseccomp -o /usr/local/bin/intervai-guard && rm /tmp/guard.c && useradd --uid 10001 --no-create-home runner
COPY sandbox /opt/runner
USER 10001:10001
WORKDIR /opt/runner
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "server.py"]

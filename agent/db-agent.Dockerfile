FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      iproute2 \
      postgresql-client \
      procps \
    && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agent/agent_server.py /app/agent_server.py
COPY agent/db_allowed_commands.json /app/db_allowed_commands.json

CMD ["python3", "/app/agent_server.py"]

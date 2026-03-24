FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      iproute2 \
      procps \
    && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY demo/app/requirements.txt /app/requirements.txt

RUN pip install \
    --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r /app/requirements.txt

COPY demo/app/app.py /app/app.py
COPY agent/agent_server.py /app/agent_server.py
COPY demo/app/allowed_commands.json /app/allowed_commands.json
COPY demo/app/run_demo_app.sh /app/run_demo_app.sh

RUN chmod +x /app/run_demo_app.sh

CMD ["sh", "/app/run_demo_app.sh"]

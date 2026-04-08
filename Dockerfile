FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /code

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential libgomp1 netcat-openbsd libreoffice catdoc openssh-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /code/requirements.txt

RUN pip install \
    --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r /code/requirements.txt

COPY . /code

RUN chmod +x /code/entrypoint.sh

EXPOSE 8000

CMD ["sh", "/code/entrypoint.sh"]

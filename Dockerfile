FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY kubbernetd/ kubbernetd/

RUN pip install --no-cache-dir .

ENTRYPOINT ["kubbernetd-operator"]
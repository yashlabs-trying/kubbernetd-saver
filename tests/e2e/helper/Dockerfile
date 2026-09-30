FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV E2E_HELPER_PORT=80

EXPOSE 80

ENTRYPOINT ["python", "/app/server.py"]
CMD ["normal"]

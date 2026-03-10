FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# HOST must be 0.0.0.0 to accept traffic inside Cloud Run
# PORT is injected by Cloud Run at runtime — do not hardcode it here
ENV HOST=0.0.0.0

EXPOSE 8080

CMD ["python3", "server.py"]

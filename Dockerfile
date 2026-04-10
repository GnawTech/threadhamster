FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends sqlite3 && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Prepare data directory
RUN mkdir -p /app/data && \
    chmod -R 777 /app/data

VOLUME ["/app/data"]

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Berlin

CMD ["python3", "main.py"]

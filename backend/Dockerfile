FROM python:3.13-slim

WORKDIR /app

# System deps for cryptography/Pillow wheels build cleanly on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /data is where the Fly volume is mounted (see fly.toml). The DB and
# uploads live there so they survive redeploys instead of the ephemeral
# container filesystem.
ENV DATABASE_URL=sqlite:////data/networking.db
ENV UPLOADS_DIR=/data/uploads
RUN mkdir -p /data/uploads

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

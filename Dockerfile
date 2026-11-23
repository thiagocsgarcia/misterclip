FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web
COPY profiles profiles
COPY tests tests
ENV MC_DATA=/data MC_MODE=fake PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8490
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8490"]

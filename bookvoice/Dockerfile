FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg poppler-utils antiword libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY web/ ./web/
ENV DATA_DIR=/data MODEL_DIR=/models PORT=8140 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
EXPOSE 8140
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8140/health',timeout=3)"
CMD ["python","src/app.py","serve"]

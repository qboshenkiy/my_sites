FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends systemd && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
COPY src/ src/
COPY web/ web/
EXPOSE 8150
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8150/health',timeout=3)"
CMD ["python", "src/app.py"]

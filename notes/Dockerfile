FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data TZ=Asia/Bishkek
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 app && mkdir /data && chown app /data
COPY src/ src/
COPY web/ web/
USER app
EXPOSE 8170
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8170/health',timeout=3)"
CMD ["gunicorn", "--chdir", "src", "--bind", "0.0.0.0:8170", "--workers", "2", "--threads", "2", "app:app"]

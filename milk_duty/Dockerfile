FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data BIND=0.0.0.0 PORT=8130
COPY src/ ./src/
COPY web/ ./web/
RUN mkdir /data && chmod 700 /data
VOLUME ["/data"]
EXPOSE 8130
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8130/health',timeout=3)"
CMD ["python", "src/app.py", "serve"]

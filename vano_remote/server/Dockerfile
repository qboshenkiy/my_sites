FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/app.py .
RUN useradd --uid 10001 --create-home vano && mkdir /data && chown vano:vano /data
USER vano
EXPOSE 8080
CMD ["python", "app.py"]

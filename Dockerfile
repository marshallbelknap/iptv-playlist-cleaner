FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8765 CACHE_DIR=/cache PYTHONUNBUFFERED=1
RUN mkdir -p /cache
EXPOSE 8765
HEALTHCHECK --interval=5m --timeout=10s CMD python3 -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/health'%os.environ.get('PORT','8765'))"
CMD ["python3", "serve.py"]

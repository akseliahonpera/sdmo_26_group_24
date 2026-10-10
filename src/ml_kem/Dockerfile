   FROM python:3.12-slim
   WORKDIR /app
   RUN pip install --no-cache-dir kyber-py cryptography requests
   COPY proxy.py .
   CMD ["python", "proxy.py"]
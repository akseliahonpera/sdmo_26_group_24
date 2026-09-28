FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY cloud_server/requirements.txt cloud_server/requirements.txt
RUN pip install --no-cache-dir -r cloud_server/requirements.txt

COPY cloud_server/ cloud_server/

EXPOSE 5000
CMD ["python", "-m", "cloud_server.app"]
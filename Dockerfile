FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROOM_DB=/data/room.db

WORKDIR /app

COPY room_service/requirements.txt /app/room_service/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/room_service/requirements.txt

COPY . /app
RUN mkdir -p /data

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn room_service.deploy_app:create_deploy_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]

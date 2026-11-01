FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Run as a non-root user; /app/data holds the email history Excel file (a volume in production)
RUN useradd --system --uid 10001 app && mkdir -p /app/data && chown app /app/data
USER app
EXPOSE 8000
# One process: the daily send job runs inside it (APScheduler). Nginx writes the access log, so uvicorn's is off.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.middleware.asgi:app --host 0.0.0.0 --port 8000 --no-access-log"]

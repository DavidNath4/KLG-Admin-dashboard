FROM python:3.11-slim

# Logging & no .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000

WORKDIR /app

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

EXPOSE 3000

# Gunicorn: port fleksibel + log ke stdout/stderr
CMD sh -c 'gunicorn --bind 0.0.0.0:${PORT:-3000} --access-logfile - --error-logfile - app:create_app()'

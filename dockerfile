FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy dependency list
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port (Flask default 3000)
EXPOSE 3000

# app:app -> file app.py, object Flask bernama app
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "app:app"]

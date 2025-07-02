### 2. `Dockerfile`
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy current directory contents
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose FastAPI port
EXPOSE 10000

# Start the API server
CMD ["uvicorn", "brfc_fastapi_agent:app", "--host", "0.0.0.0", "--port", "10000"]

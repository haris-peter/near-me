# Use a slim Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy dependencies first (for caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MCP_SERVER_ID=near-me-tool
ENV MAX_RESULTS=6
ENV DEFAULT_RADIUS_KM=5.0

# Run the MCP server
CMD ["python", "server.py"]

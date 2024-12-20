# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . /app/

# Expose the port the app runs on
EXPOSE 5000

# Create a volume for persistent data
VOLUME ["/app/uploads", "/app/instance"]

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "run:app"]
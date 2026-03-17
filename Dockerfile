# Use the official Playwright Python image
# This image comes with all necessary system dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser (dependencies are already in the base image)
RUN playwright install chromium

# Copy the rest of the application code
COPY . .

# Expose the port for the health check server
EXPOSE 10000

# Run the bot
CMD ["python", "bot.py"]

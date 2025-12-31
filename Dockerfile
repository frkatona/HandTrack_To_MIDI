# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install system dependencies required for OpenCV and MediaPipe
# libgl1 and libglib2.0 are necessary for OpenCV's GUI and image processing
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Download the MediaPipe gesture model during build
RUN python download_model.py

# Define environment variable to help OpenCV find the display (for Linux users)
ENV DISPLAY=:0

# The command to run when the container starts
# We use -u to ensure output is unbuffered so you see logs immediately
CMD ["python", "-u", "HandTrackToMIDI.py"]

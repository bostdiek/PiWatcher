# Use a base Python image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the wheel file from the build context into the image
ARG WHEEL_PATH
COPY ${WHEEL_PATH} /app/

# Install dependencies from the wheel file
RUN pip install /app/*.whl

# Install additional dependencies if needed
RUN pip install some-other-package

# Set the command to run the app
CMD ["python", "app.py"]

FROM python:3.8-slim

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev

# Install poetry
RUN pip install poetry

# Copy and install the wheel
COPY piwatcher_base-*.whl /tmp/
RUN pip install /tmp/piwatcher_base-*.whl

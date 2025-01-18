# Stage 1: Build stage for Raspberry Pi Zero (arm6)

FROM --platform=linux/arm/v6 debian:bookworm

# Install necessary packages
RUN apt-get update && \
    apt-get install -y \
    wget \
    tar \
    libcamera-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Download and extract the pre-built binaries
RUN wget https://github.com/bluenviron/mediamtx/releases/download/v1.11.1/mediamtx_v1.11.1_linux_armv6.tar.gz && \
    tar -xzf mediamtx_v1.11.1_linux_armv6.tar.gz && \
    rm mediamtx_v1.11.1_linux_armv6.tar.gz

# Ensure the binary is executable
RUN chmod +x mediamtx

# Set the entrypoint to the binary
ENTRYPOINT ["./mediamtx"]

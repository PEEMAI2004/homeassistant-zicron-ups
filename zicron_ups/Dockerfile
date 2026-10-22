ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    nut \
    libusb \
    eudev

RUN pip3 install --no-cache-dir --break-system-packages pyusb requests

WORKDIR /app

COPY zicron_ups_daemon.py /app/
COPY run.sh /app/

RUN chmod +x /app/run.sh /app/zicron_ups_daemon.py

CMD [ "/app/run.sh" ]

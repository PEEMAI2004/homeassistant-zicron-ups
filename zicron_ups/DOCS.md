# Zicron UPS Monitor Documentation

This add-on connects to the Zicron UPS via the passed-through USB device (`0001:0000`).

### Configuration
- **poll_interval**: Interval in seconds between telemetry polls (default: `2`).

### Connecting Home Assistant
After starting the add-on, go to **Settings** -> **Devices & Services** -> **Add Integration** -> **Network UPS Tools (NUT)**:
- **Host**: `127.0.0.1`
- **Port**: `3493`
- **Username**: `ha`
- **Password**: `homeassistant`

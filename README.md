# Home Assistant Add-on: Zicron UPS Monitor

Home Assistant Add-on providing real-time telemetry, Web Dashboard, and Network UPS Tools (NUT) server for Zicron UPS devices communicating via Cypress USB HID bridge (`0001:0000` / UPSmart protocol).

## Features
- **Native NUT Server**: Runs on `localhost:3493` for Home Assistant's built-in **Network UPS Tools (NUT)** integration.
- **Embedded Web Dashboard**: View real-time voltages, battery percentage, load, frequency, and status right inside Home Assistant via Ingress.
- **REST & Prometheus API**: Exposes JSON telemetry and Prometheus metrics on port `9120`.

## Installation
1. In Home Assistant, go to **Settings** -> **Add-ons** -> **Add-on Store**.
2. Click the top-right 3 dots (⋮) and select **Repositories**.
3. Add this repository URL:
   `https://github.com/PEEMAI2004/homeassistant-zicron-ups`
4. Find **Zicron UPS Monitor** in the list and click **Install**.
5. Enable **Start on boot** and **Watchdog**, then click **Start**.
6. Click **Open Web UI** to view the live dashboard!

## Home Assistant Entities Setup
Once the Add-on is started:
1. Go to **Settings** -> **Devices & Services** -> **Add Integration**.
2. Select **Network UPS Tools (NUT)**.
3. Configure:
   - **Host**: `127.0.0.1` (or `localhost`)
   - **Port**: `3493`
   - **Username**: `ha`
   - **Password**: `homeassistant`
4. Click **Submit**. Home Assistant will immediately populate all battery, voltage, load, and status sensors!

#!/usr/bin/env python3
"""
Zicron UPS Monitoring Daemon for Home Assistant Add-on & Network UPS Tools (NUT)
Reverse engineered from UPSmart (Fry's Electronics / MEC0003 Cypress USB HID Bridge 0001:0000)
"""

import os
import sys
import time
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import usb.core
import usb.util

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("zicron_ups")

NUT_DEV_FILE = "/etc/nut/zicron.dev"
HTTP_PORT = 9120

latest_data = {
    "connected": False,
    "last_update": 0,
    "mfr": "Zicron",
    "model": "UPSmart-HID",
    "version": "",
    "rating_voltage": 220.0,
    "rating_current": 0.0,
    "battery_nominal_voltage": 12.0,
    "input_voltage": 0.0,
    "fault_voltage": 0.0,
    "output_voltage": 0.0,
    "load_percent": 0,
    "frequency": 0.0,
    "battery_voltage": 0.0,
    "battery_charge": 0.0,
    "temperature": 0.0,
    "ups_status": "WAIT",
    "raw_bits": "00000000",
    "utility_fail": False,
    "battery_low": False,
    "avr_active": False,
    "ups_fault": False,
    "line_interactive": True,
    "test_in_progress": False,
    "shutdown_active": False,
    "beeper_on": False,
    "error": None
}
data_lock = threading.Lock()

def calculate_battery_percentage(volts: float, nominal: float = 12.0) -> float:
    """Calculate battery charge percentage based on sealed lead-acid discharge curve."""
    if volts <= 0:
        return 0.0
    scale = nominal / 12.0
    v = volts / scale
    curve = [
        (10.5, 0.0),
        (11.0, 10.0),
        (11.5, 20.0),
        (11.8, 30.0),
        (12.0, 45.0),
        (12.2, 60.0),
        (12.4, 75.0),
        (12.6, 85.0),
        (12.8, 92.0),
        (13.2, 98.0),
        (13.6, 100.0)
    ]
    if v <= curve[0][0]:
        return 0.0
    if v >= curve[-1][0]:
        return 100.0
    for i in range(len(curve) - 1):
        v1, p1 = curve[i]
        v2, p2 = curve[i + 1]
        if v1 <= v <= v2:
            return round(p1 + (v - v1) / (v2 - v1) * (p2 - p1), 1)
    return 100.0

def query_string_descriptor(dev, index: int) -> str:
    """Read a string descriptor via standard USB Control Transfer."""
    wValue = (0x03 << 8) | (index & 0xff)
    resp = dev.ctrl_transfer(0x80, 0x06, wValue, 0x0409, 255, 1000)
    if len(resp) < 2:
        return ""
    return bytes(resp)[2:].decode('utf-16le', errors='ignore').strip()

def parse_q1(raw: str):
    raw = raw.strip()
    if raw.startswith('('):
        raw = raw[1:]
    parts = raw.split()
    if len(parts) < 8:
        raise ValueError(f"Invalid Q1 data length ({len(parts)} parts): {raw}")
    
    input_v = float(parts[0])
    fault_v = float(parts[1])
    output_v = float(parts[2])
    load_pct = int(parts[3])
    freq = float(parts[4])
    batt_v = float(parts[5])
    temp = float(parts[6])
    bits = parts[7]

    b7 = bits[0] == '1' # Utility Fail (1 = On Battery, 0 = Normal AC)
    b6 = bits[1] == '1' # Battery Low
    b5 = bits[2] == '1' # AVR Boost/Buck
    b4 = bits[3] == '1' # UPS Failed
    b3 = bits[4] == '1' # UPS Type (1 = Line-interactive, 0 = Online)
    b2 = bits[5] == '1' # Self Test in Progress
    b1 = bits[6] == '1' # Shutdown Active
    b0 = bits[7] == '1' # Beeper Active

    batt_charge = calculate_battery_percentage(batt_v)

    status_tokens = []
    if b7:
        status_tokens.append("OB")
        status_tokens.append("DISCHRG")
    else:
        status_tokens.append("OL")
        if batt_v < 13.6 and batt_charge < 100:
            status_tokens.append("CHRG")

    if b6 or batt_charge <= 20:
        status_tokens.append("LB")
    if b5:
        if input_v < output_v:
            status_tokens.append("BOOST")
        else:
            status_tokens.append("TRIM")
    if b4:
        status_tokens.append("RB")
    if b2:
        status_tokens.append("TEST")
    if b1:
        status_tokens.append("OFF")

    ups_status = " ".join(status_tokens) if status_tokens else "OL"

    return {
        "input_voltage": input_v,
        "fault_voltage": fault_v,
        "output_voltage": output_v,
        "load_percent": load_pct,
        "frequency": freq,
        "battery_voltage": batt_v,
        "battery_charge": batt_charge,
        "temperature": temp,
        "raw_bits": bits,
        "utility_fail": b7,
        "battery_low": b6,
        "avr_active": b5,
        "ups_fault": b4,
        "line_interactive": b3,
        "test_in_progress": b2,
        "shutdown_active": b1,
        "beeper_on": b0,
        "ups_status": ups_status
    }

def update_nut_file(data):
    tmp_path = NUT_DEV_FILE + ".tmp"
    content = f"""device.mfr: {data.get('mfr', 'Zicron')}
device.model: {data.get('model', 'UPSmart-HID')}
device.type: ups
battery.charge: {data.get('battery_charge', 100.0)}
battery.voltage: {data.get('battery_voltage', 13.7)}
battery.voltage.nominal: {data.get('battery_nominal_voltage', 12.0)}
input.voltage: {data.get('input_voltage', 230.0)}
input.voltage.fault: {data.get('fault_voltage', 0.0)}
input.frequency: {data.get('frequency', 50.0)}
output.voltage: {data.get('output_voltage', 230.0)}
output.frequency: {data.get('frequency', 50.0)}
ups.load: {data.get('load_percent', 0)}
ups.temperature: {data.get('temperature', 25.0)}
ups.status: {data.get('ups_status', 'OL')}
ups.beeper.status: {'enabled' if data.get('beeper_on', False) else 'disabled'}
"""
    try:
        with open(tmp_path, "w") as f:
            f.write(content)
        os.replace(tmp_path, NUT_DEV_FILE)
    except Exception as e:
        logger.error(f"Failed to write NUT file {NUT_DEV_FILE}: {e}")

class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        with data_lock:
            data = dict(latest_data)

        clean_path = self.path.split('?')[0].rstrip('/')

        if clean_path.endswith('/api/status') or clean_path.endswith('/json'):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())
            return

        if clean_path.endswith('/metrics'):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            lines = [
                f"# HELP ups_connected UPS USB Connection Status (1=connected, 0=disconnected)",
                f"# TYPE ups_connected gauge",
                f"ups_connected {1 if data['connected'] else 0}",
                f"# HELP ups_input_voltage Input AC Voltage in Volts",
                f"# TYPE ups_input_voltage gauge",
                f"ups_input_voltage {data['input_voltage']}",
                f"# HELP ups_output_voltage Output AC Voltage in Volts",
                f"# TYPE ups_output_voltage gauge",
                f"ups_output_voltage {data['output_voltage']}",
                f"# HELP ups_load_percent Output Load Percentage (0-100)",
                f"# TYPE ups_load_percent gauge",
                f"ups_load_percent {data['load_percent']}",
                f"# HELP ups_frequency Output Frequency in Hz",
                f"# TYPE ups_frequency gauge",
                f"ups_frequency {data['frequency']}",
                f"# HELP ups_battery_voltage Battery Voltage in Volts",
                f"# TYPE ups_battery_voltage gauge",
                f"ups_battery_voltage {data['battery_voltage']}",
                f"# HELP ups_battery_charge Battery Charge Percentage (0-100)",
                f"# TYPE ups_battery_charge gauge",
                f"ups_battery_charge {data['battery_charge']}",
                f"# HELP ups_temperature Internal Temperature in Celsius",
                f"# TYPE ups_temperature gauge",
                f"ups_temperature {data['temperature']}",
                f"# HELP ups_on_battery On Battery Indicator (1=on battery, 0=utility power)",
                f"# TYPE ups_on_battery gauge",
                f"ups_on_battery {1 if data['utility_fail'] else 0}",
                f"# HELP ups_battery_low Battery Low Indicator (1=low, 0=ok)",
                f"# TYPE ups_battery_low gauge",
                f"ups_battery_low {1 if data['battery_low'] else 0}",
            ]
            self.wfile.write(("\n".join(lines) + "\n").encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Zicron UPS Telemetry</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; max-width: 600px; margin: 0 auto; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5); }}
        h1 {{ margin-top: 0; color: #38bdf8; font-size: 1.5rem; display: flex; justify-content: space-between; align-items: center; }}
        .badge {{ font-size: 0.9rem; padding: 4px 10px; border-radius: 6px; }}
        .badge-online {{ background: #10b981; color: #fff; }}
        .badge-battery {{ background: #f59e0b; color: #fff; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }}
        .metric {{ background: #334155; padding: 1rem; border-radius: 8px; }}
        .metric-title {{ font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }}
        .metric-val {{ font-size: 1.6rem; font-weight: bold; margin-top: 0.2rem; }}
        .footer {{ font-size: 0.8rem; color: #64748b; margin-top: 1.5rem; text-align: center; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>
            <span>⚡ Zicron UPS</span>
            <span class="badge {'badge-online' if not data['utility_fail'] else 'badge-battery'}">{data['ups_status']}</span>
        </h1>
        <div class="grid">
            <div class="metric">
                <div class="metric-title">Input Voltage</div>
                <div class="metric-val">{data['input_voltage']} V</div>
            </div>
            <div class="metric">
                <div class="metric-title">Output Voltage</div>
                <div class="metric-val">{data['output_voltage']} V</div>
            </div>
            <div class="metric">
                <div class="metric-title">Output Load</div>
                <div class="metric-val">{data['load_percent']} %</div>
            </div>
            <div class="metric">
                <div class="metric-title">Frequency</div>
                <div class="metric-val">{data['frequency']} Hz</div>
            </div>
            <div class="metric">
                <div class="metric-title">Battery Voltage</div>
                <div class="metric-val">{data['battery_voltage']} V</div>
            </div>
            <div class="metric">
                <div class="metric-title">Battery Level</div>
                <div class="metric-val">{data['battery_charge']} %</div>
            </div>
            <div class="metric">
                <div class="metric-title">Temperature</div>
                <div class="metric-val">{data['temperature']} °C</div>
            </div>
            <div class="metric">
                <div class="metric-title">Status Bits</div>
                <div class="metric-val" style="font-family: monospace; font-size: 1.2rem;">{data['raw_bits']}</div>
            </div>
        </div>
        <div class="footer">
            NUT server: port 3493 (localhost) | Status: {'CONNECTED' if data['connected'] else 'WAITING'}
        </div>
    </div>
</body>
</html>"""
        self.wfile.write(html.encode())

def run_http_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), MetricsHandler)
    logger.info(f"HTTP Server listening on http://0.0.0.0:{HTTP_PORT}")
    server.serve_forever()

def main():
    logger.info("Starting Zicron UPS Add-on Daemon...")
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    while True:
        dev = None
        try:
            logger.info("Searching for Zicron UPS (USB 0001:0000)...")
            dev = usb.core.find(idVendor=0x0001, idProduct=0x0000)
            if dev is None:
                logger.warning("UPS device not found. Retrying in 5 seconds...")
                time.sleep(5)
                continue

            logger.info("UPS device located! Initializing communication...")
            for cfg in dev:
                for intf in cfg:
                    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                        try:
                            dev.detach_kernel_driver(intf.bInterfaceNumber)
                            logger.info(f"Detached kernel driver on interface {intf.bInterfaceNumber}")
                        except Exception as e:
                            logger.warning(f"Could not detach kernel driver: {e}")

            try:
                info_str = query_string_descriptor(dev, 0x0c)
                logger.info(f"UPS Model Information: {info_str}")
                rating_str = query_string_descriptor(dev, 0x0d)
                logger.info(f"UPS Rating Information: {rating_str}")
            except Exception as e:
                logger.warning(f"Failed to read static info strings: {e}")

            logger.info("Entering telemetry polling loop (interval: 2s)...")
            fail_count = 0
            while True:
                try:
                    q1_raw = query_string_descriptor(dev, 0x03)
                    if not q1_raw:
                        raise ValueError("Empty Q1 response received")
                    
                    parsed = parse_q1(q1_raw)
                    fail_count = 0

                    with data_lock:
                        latest_data.update(parsed)
                        latest_data["connected"] = True
                        latest_data["last_update"] = time.time()
                        latest_data["error"] = None

                    update_nut_file(latest_data)
                    time.sleep(2)

                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Poll error ({fail_count}): {e}")
                    if fail_count >= 3:
                        logger.error("Too many poll failures. Reconnecting device...")
                        break
                    time.sleep(2)

        except Exception as e:
            logger.error(f"Fatal device loop error: {e}")
            with data_lock:
                latest_data["connected"] = False
                latest_data["error"] = str(e)
                latest_data["ups_status"] = "OFFLINE"
            update_nut_file(latest_data)
            time.sleep(5)

if __name__ == "__main__":
    main()

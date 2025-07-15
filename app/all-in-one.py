#!/usr/bin/env python3

import colorsys
import sys
import time
import json
from datetime import datetime, timedelta

import st7735
from azure.storage.blob import BlobServiceClient

try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559

import logging

from bme280 import bme280
from fonts.ttf import RobotoMedium as UserFont
from PIL import Image, ImageDraw, ImageFont
from pms5003 import PMS5003
from pms5003 import ReadTimeoutError as pmsReadTimeoutError

from enviroplus import gas

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S")

logging.info("""all-in-one.py - Displays readings from all of Enviro plus' sensors

Press Ctrl+C to exit!

""")

# BME280 temperature/pressure/humidity sensor
bme280 = bme280()

# PMS5003 particulate sensor
pms5003 = PMS5003()

# Create ST7735 LCD display class
st7735 = st7735.ST7735(
    port=0,
    cs=1,
    dc="GPIO9",
    backlight="GPIO12",
    rotation=270,
    spi_speed_hz=10000000
)

# Initialize display
st7735.begin()

WIDTH = st7735.width
HEIGHT = st7735.height

# Set up canvas and font
img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
font_size = 20
font = ImageFont.truetype(UserFont, font_size)

message = ""

# The position of the top bar
top_pos = 25


# Displays data and text on the 0.96" LCD
def display_text(variable, data, unit):
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    # Scale the values for the variable between 0 and 1
    vmin = min(values[variable])
    vmax = max(values[variable])
    colours = [(v - vmin + 1) / (vmax - vmin + 1) for v in values[variable]]
    # Format the variable name and value
    message = f"{variable[:4]}: {data:.1f} {unit}"
    logging.info(message)
    draw.rectangle((0, 0, WIDTH, HEIGHT), (255, 255, 255))
    for i in range(len(colours)):
        # Convert the values to colours from red to blue
        colour = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(colour, 1.0, 1.0)]
        # Draw a 1-pixel wide rectangle of colour
        draw.rectangle((i, top_pos, i + 1, HEIGHT), (r, g, b))
        # Draw a line graph in black
        line_y = HEIGHT - (top_pos + (colours[i] * (HEIGHT - top_pos))) + top_pos
        draw.rectangle((i, line_y, i + 1, line_y + 1), (0, 0, 0))
    # Write the text at the top in black
    draw.text((0, 0), message, font=font, fill=(0, 0, 0))
    st7735.display(img)


# Get the temperature of the CPU for compensation
def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = f.read()
        temp = int(temp) / 1000.0
    return temp


# Tuning factor for compensation. Decrease this number to adjust the
# temperature down, and increase to adjust up
factor = 2.25

cpu_temps = [get_cpu_temperature()] * 5

delay = 0.5  # Debounce the proximity tap
mode = 0     # The starting mode
last_page = 0
light = 1

# Create a values dict to store the data
variables = ["temperature",
             "pressure",
             "humidity",
             "light",
             "oxidised",
             "reduced",
             "nh3",
             "pm1",
             "pm25",
             "pm10"]

values = {}

for v in variables:
    values[v] = [1] * WIDTH

# Azure Blob Storage configuration
AZURE_STORAGE_CONNECTION_STRING = "<YOUR_AZURE_STORAGE_CONNECTION_STRING>"
AZURE_CONTAINER_NAME = "<YOUR_CONTAINER_NAME>"

# Buffer for 5-minute averages
AVG_INTERVAL = 300  # seconds
sample_buffer = {v: [] for v in variables}
start_time = datetime.utcnow()

# Initialize Azure Blob client
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

# The main loop
try:
    while True:
        proximity = ltr559.get_proximity()

        # Collect all sensor data every loop
        cpu_temp = get_cpu_temperature()
        cpu_temps = cpu_temps[1:] + [cpu_temp]
        avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
        raw_temp = bme280.get_temperature()
        temperature = raw_temp - ((avg_cpu_temp - raw_temp) / factor)
        pressure = bme280.get_pressure()
        humidity = bme280.get_humidity()
        if proximity < 10:
            light_val = ltr559.get_lux()
        else:
            light_val = 1
        gas_data = gas.read_all()
        oxidised = gas_data.oxidising / 1000
        reduced = gas_data.reducing / 1000
        nh3 = gas_data.nh3 / 1000
        try:
            pm_data = pms5003.read()
            pm1 = float(pm_data.pm_ug_per_m3(1.0))
            pm25 = float(pm_data.pm_ug_per_m3(2.5))
            pm10 = float(pm_data.pm_ug_per_m3(10))
        except pmsReadTimeoutError:
            logging.warning("Failed to read PMS5003")
            pm1 = pm25 = pm10 = None

        # Append all metrics to their buffers
        sample_buffer["temperature"].append(temperature)
        sample_buffer["pressure"].append(pressure)
        sample_buffer["humidity"].append(humidity)
        sample_buffer["light"].append(light_val)
        sample_buffer["oxidised"].append(oxidised)
        sample_buffer["reduced"].append(reduced)
        sample_buffer["nh3"].append(nh3)
        if pm1 is not None:
            sample_buffer["pm1"].append(pm1)
        if pm25 is not None:
            sample_buffer["pm25"].append(pm25)
        if pm10 is not None:
            sample_buffer["pm10"].append(pm10)

        # If the proximity crosses the threshold, toggle the mode
        if proximity > 1500 and time.time() - last_page > delay:
            mode += 1
            mode %= len(variables)
            last_page = time.time()

        # Display only the current mode
        if mode == 0:
            unit = "°C"
            display_text("temperature", temperature, unit)
        if mode == 1:
            unit = "hPa"
            display_text("pressure", pressure, unit)
        if mode == 2:
            unit = "%"
            display_text("humidity", humidity, unit)
        if mode == 3:
            unit = "Lux"
            display_text("light", light_val, unit)
        if mode == 4:
            unit = "kO"
            display_text("oxidised", oxidised, unit)
        if mode == 5:
            unit = "kO"
            display_text("reduced", reduced, unit)
        if mode == 6:
            unit = "kO"
            display_text("nh3", nh3, unit)
        if mode == 7:
            unit = "ug/m3"
            if pm1 is not None:
                display_text("pm1", pm1, unit)
        if mode == 8:
            unit = "ug/m3"
            if pm25 is not None:
                display_text("pm25", pm25, unit)
        if mode == 9:
            unit = "ug/m3"
            if pm10 is not None:
                display_text("pm10", pm10, unit)

        # Every 5 minutes, compute averages and send to Azure
        now = datetime.utcnow()
        if (now - start_time).total_seconds() >= AVG_INTERVAL:
            avg_data = {}
            for v in variables:
                if sample_buffer[v]:
                    avg_data[v] = sum(sample_buffer[v]) / len(sample_buffer[v])
                else:
                    avg_data[v] = None
            # ECS formatting
            ecs_doc = {
                "@timestamp": now.isoformat() + "Z",
                "event": {"kind": "metric", "category": ["environmental"], "type": ["info"]},
                "host": {"hostname": "enviroplus"},
                "sensor": {
                    "temperature": avg_data["temperature"],
                    "pressure": avg_data["pressure"],
                    "humidity": avg_data["humidity"],
                    "light": avg_data["light"],
                    "gas": {
                        "oxidised": avg_data["oxidised"],
                        "reduced": avg_data["reduced"],
                        "nh3": avg_data["nh3"]
                    },
                    "pm": {
                        "pm1": avg_data["pm1"],
                        "pm25": avg_data["pm25"],
                        "pm10": avg_data["pm10"]
                    }
                }
            }
            # Upload to Azure Blob Storage
            blob_name = f"enviroplus_{now.strftime('%Y%m%dT%H%M%S')}.json"
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(json.dumps(ecs_doc), overwrite=True)
            logging.info(f"Uploaded ECS data to Azure Blob: {blob_name}")
            # Reset buffer and timer
            sample_buffer = {v: [] for v in variables}
            start_time = now

# Exit cleanly
except KeyboardInterrupt:
    sys.exit(0)
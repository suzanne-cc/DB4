import asyncio
from machine import Pin, PWM
from provided_code.tcs34725 import TCS34725
import utime
import math
import MQTT
import storage
import display
from pin_configuration import OD_PUMP, LED_PIN
from variables import *

# ============================================================
# SAFETY LIMITS — hard ceilings, never crossed
# ============================================================
MAX_PUMP_SECONDS    = 1.5      # absolute max pump-on time per feed
MIN_FEED_INTERVAL_S = 1800     # at least 30 min between feeds
MEASURE_PUMP_SEC    = 1.0      # short circulation pump before reading OD

# ---------- Pins ----------
pump_pin = Pin(OD_PUMP, Pin.OUT)
pump = PWM(pump_pin, freq=10000)
led = Pin(LED_PIN, Pin.OUT)

od_sensor = None  # set inside the task once i2c is available

def pump_on():
    pump.duty(511)

def pump_off():
    pump.duty(0)

# Make sure pump starts OFF at import
pump_off()

# ------- MQTT feeds -------
flow_ml_transfered = MQTT.make_feed(b'od-sensor.ml-transfered')
od_feed            = MQTT.make_feed(b'od-sensor.od-feed')
feed_target_algae  = MQTT.make_feed(b'subscribed-data.target-algae')

def handle_mqtt(topic, msg):
    global TARGET_ALGAE
    try:
        value = float(msg.decode('utf-8'))
        if topic == feed_target_algae:
            TARGET_ALGAE = value
            print('Target algae cell number: {}'.format(value))
    except ValueError:
        print('Invalid value received: {}'.format(msg))

# ============================================================
# OD MEASUREMENT (with guaranteed pump shutoff)
# ============================================================
async def measure_OD():
    print("measure start")
    try:
        pump_on()
        await asyncio.sleep(MEASURE_PUMP_SEC)
        pump_off()                 # stop circulation before reading

        led.on()
        await asyncio.sleep(1)
        _, _, sample_reading, _ = od_sensor.read(True)
        print("raw", sample_reading)
        await asyncio.sleep(1)
        led.off()
    finally:
        # No matter what happens above, pump and LED are OFF
        pump_off()
        led.off()

    if not sample_reading:
        return None
    od = math.log10(sample_reading / CLEAR_OD_READING)
    print("od:", od)
    return od

# ============================================================
# FEEDING LOGIC — duration is always capped
# ============================================================
def od_to_algae_concentration(od):
    return max(0, OD_TO_CELLS_SLOPE * od + OD_TO_CELLS_INTERCEPT)

def pump_duration_from_od(feed_od):
    """Returns a feed duration, ALWAYS clamped to MAX_PUMP_SECONDS."""
    feed_conc = od_to_algae_concentration(feed_od)

    if feed_conc <= 0:
        print("Warning: algae concentration too low — skipping feed")
        return 0.0
    if feed_conc > 400000:
        print("Warning: algae concentration too high — add fresh water")
        return 0.0

    # Default duration. The old correction_factor math mixed units
    # (cells vs OD) and produced runaway values, so it's removed.
    duration_s = DEFAULT_DURATION

    # Hard cap — this is the failsafe
    if duration_s > MAX_PUMP_SECONDS:
        print("Capped requested {:.2f}s to {:.2f}s".format(
            duration_s, MAX_PUMP_SECONDS))
        duration_s = MAX_PUMP_SECONDS

    return max(0.0, duration_s)

async def safe_pump_feed(duration_s):
    """Pump for duration_s with a guaranteed shutoff."""
    # Defensive: clamp again right before we actually run the pump
    duration_s = min(max(0.0, duration_s), MAX_PUMP_SECONDS)
    if duration_s <= 0:
        return 0.0
    try:
        pump_on()
        await asyncio.sleep(duration_s)
    finally:
        pump_off()    # runs even if task is cancelled or crashes
    return duration_s

# ============================================================
# ASYNC TASK
# ============================================================
async def od_task(i2c, client):
    global od_sensor

    od_sensor = TCS34725(i2c)
    od_sensor.integration_time(200)
    od_sensor.gain(1)

    storage.init_csv("OD_measurements",
                     ["Time [s]", "OD", "Pump Duration [s]",
                      "Volume Transfered [ml]"])
    start = utime.time()
    ml_transfered = 0
    last_feed_time = 0          # 0 = never fed yet

    try:
        while True:
            od_measured = await measure_OD()

            now = utime.time()
            since_last_feed = now - last_feed_time

            if od_measured is None:
                print("OD read failed, skipping feed")
                duration_actual = 0.0

            elif last_feed_time != 0 and since_last_feed < MIN_FEED_INTERVAL_S:
                print("Skipping feed — only {}s since last feed (min {}s)"
                      .format(since_last_feed, MIN_FEED_INTERVAL_S))
                duration_actual = 0.0

            else:
                requested = pump_duration_from_od(od_measured)
                duration_actual = await safe_pump_feed(requested)
                if duration_actual > 0:
                    last_feed_time = now
                    ml_transfered += duration_actual * PUMP_ML_PER_SEC

            # Publish/log whatever happened (including skipped feeds)
            if od_measured is not None:
                display.show_quick_overview(od_measured, ml_transfered,
                                            duration_actual)
                MQTT.publish(client, od_feed, od_measured)
                MQTT.publish(client, flow_ml_transfered, ml_transfered)
                storage.store_data(utime.time() - start, od_measured,
                                   duration_actual, ml_transfered)

            # 30-minute wait, chunked to avoid asyncio overflow on ESP32
            for _ in range(1800):
                await asyncio.sleep(1)

    finally:
        # If this task ever dies (crash, cancel, reboot), pump shuts off.
        pump_off()
        led.off()
        print("od_task exiting — pump and LED forced OFF")
from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
import utime
import MQTT
import math
import storage
from pin_configuration import OD_PUMP, SCL_PIN, SDA_PIN, LED_PIN

# ---------- Pins ----------
pump = Pin(OD_PUMP, Pin.OUT)
pump.value(1)

i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=1000)
OD_sensor = TCS34725(i2c)
led = Pin(LED_PIN, Pin.OUT)

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

flow_rate_feed = MQTT.make_feed(b'flow-rate')
od_feed = MQTT.make_feed(b'od-feed')

# ------ Variables ------
OD_TO_CELLS_SLOPE = 1.0e7
OD_TO_CELLS_INTERCEPT = 0.0

CLEARING_RATE_ML_SEC = 120.0
CLEAR_OD_READING = 1000

INITIAL_CONCENTRATION = 10000
TARGET_ALGAE = 1.0e9

TIME_TO_OD = 1
PUMP_ML_PER_SEC = 10

feed_target_algae = MQTT.make_feed(b'target-algae')

def on_message(topic, msg):
    global TARGET_ALGAE
    try:
        value = float(msg.decode('utf-8'))
        if topic == feed_target_algae:
            TARGET_ALGAE = value
            print('Target algae cell number: {}'.format(value))
    except ValueError:
        print('Invalid value received: {}'.format(msg))

MQTT.subscribe(client, feed_target_algae, on_message)

# ----- Measure OD Value -----
def measure_OD():
    print("measure start")
    pump.on()
    utime.sleep(TIME_TO_OD)

    led.on()
    utime.sleep(1)
    _, _, sample_reading, _ = OD_sensor.read(True)
    utime.sleep(1)
    led.off()
    
    print("measure end")
    return math.log10(CLEAR_OD_READING / sample_reading) if sample_reading else None

# ------ Mussel Feeding ------
def od_to_algae_concentration(od):
    return max(0, OD_TO_CELLS_SLOPE * od + OD_TO_CELLS_INTERCEPT)

last_feed = utime.time()

def pump_duration_from_od(feed_od):
    global last_feed
    feed_conc = od_to_algae_concentration(feed_od)
    if feed_conc <= 0:
        return 0

    total_algae = INITIAL_CONCENTRATION - (CLEARING_RATE_ML_SEC * (utime.time() - last_feed))
    algae_needed = TARGET_ALGAE - total_algae
    flow_ml = algae_needed / feed_conc        # ml needed
    duration_s = flow_ml / (PUMP_ML_PER_SEC)  # seconds to run

    last_feed = utime.time()
    return max(0, duration_s)

# -------- Main Loop --------
storage.init_csv("OD_measurements", ["Time [s]", "OD", "Pump Duration [s]", "Volume Transfered [ml]"])
start = utime.time()

while True:
    MQTT.check_messages(client)
    od_measured = measure_OD()

    if od_measured is not None:
        duration_s = pump_duration_from_od(od_measured)

        pump.on()
        utime.sleep(duration_s)   # run for calculated duration
        pump.off()             # then stop

        ml_transfered = duration_s * PUMP_ML_PER_SEC

        MQTT.publish(client, od_feed, od_measured)
        MQTT.publish(client, flow_rate_feed, ml_transfered)
        storage.store_data(utime.time() - start, od_measured, duration_s, ml_transfered)
    else:
        pump.off()

    utime.sleep(60)
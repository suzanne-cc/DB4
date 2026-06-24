from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
import utime
import MQTT
import math
import storage
from pin_configuration import OD_PUMP, SCL_PIN, SDA_PIN, LED_PIN
from variables import *
import display

# ---------- Pins ----------
pump_pin = Pin(OD_PUMP, Pin.OUT)
pump = PWM(pump_pin, frequency=1000)

i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=1000)
OD_sensor = TCS34725(i2c)
OD_sensor.integration_time(500.4)
OD_sensor.gain(60)
led = Pin(LED_PIN, Pin.OUT)

# ----- Pump Settings ----
def pump_on():
    pump.duty(511.5)

def pump_off():
    pump.duty(0)

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

flow_ml_transfered = MQTT.make_feed(b'od-sensor.ml-transfered')
od_feed = MQTT.make_feed(b'od-sensor.od-feed')

# ------ Update Target Algae ------
feed_target_algae = MQTT.make_feed(b'subscribed-data.target-algae')

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
    pump_on()
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
    global last_feed, DEFAULT_DURATION
    feed_conc = od_to_algae_concentration(feed_od)

    correction_factor = TARGET_OD / feed_od

    if feed_conc <= 0:
        print("Warning: Algae Concentration is too low, add algae")
    if 0 < feed_conc < 170000 or feed_conc > 350000:
        duration_s = DEFAULT_DURATION * correction_factor
    if feed_conc > 600000:
        print("Warning: Algae Concentration is too high, add fresh water")
    else:
        duration_s = DEFAULT_DURATION

    last_feed = utime.time()
    return max(0, duration_s)

# -------- Main Loop --------
storage.init_csv("OD_measurements", ["Time [s]", "OD", "Pump Duration [s]", "Volume Transfered [ml]"])
display.init_display(i2c)
start = utime.time()

while True:
    MQTT.check_messages(client)
    od_measured = measure_OD()

    if od_measured is not None:
        duration_s = pump_duration_from_od(od_measured)

        pump_on()
        utime.sleep(duration_s)   # run for calculated duration
        pump_off()             # then stop

        ml_transfered = duration_s * PUMP_ML_PER_SEC

        display.show_quick_overview(od_measured, ml_transfered, duration_s)

        MQTT.publish(client, od_feed, od_measured)
        MQTT.publish(client, flow_ml_transfered, ml_transfered)
        storage.store_data(utime.time() - start, od_measured, duration_s, ml_transfered)
    else:
        pump_off()

    utime.sleep(60)
from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
import utime
import MQTT
import math

# ---------- Pins ----------
pump_speed = PWM(Pin(13), freq=1000)  # speed control
in1 = Pin(14, Pin.OUT)          # direction
in2 = Pin(15, Pin.OUT)          # direction

i2c = I2C(scl=Pin(22), sda=Pin(23), freq=100000)
OD_sensor = TCS34725(i2c)

led = Pin(26, Pin.OUT)

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

flow_rate = MQTT.make_feed(b'flow-rate')
od_feed = MQTT.make_feed(b'od-feed')

# ------ Variables to be Defined ------
OD_TO_CELLS_SLOPE = 1.0e7
OD_TO_CELLS_INTERCEPT = 0.0

CLEARING_RATE_ML_MIN = 120.0

CLEAR_OD_READING = 1000
PUMP_ML_MIN_PER_DUTY = 0.05 

# ------ Update Target Algae Concentration -------
TARGET_ALGAE_CONC = 1.0e6  # default until updated from dashboard

feed_target_algae = MQTT.make_feed(b'target-algae')

def on_message(topic, msg):
    global TARGET_ALGAE_CONC
    try:
        value = float(msg.decode('utf-8'))

        if topic == feed_target_algae:
            TARGET_ALGAE_CONC = value
            print('Target algae concentration updated to: {}'.format(value))
        else:
            print('Unknown topic: {}'.format(topic))

    except ValueError:
        print('Invalid value received: {}'.format(msg))

MQTT.subscribe(client, feed_target_algae, on_message)

# ----- Pump direction -----
def pump_to_mussel(speed):
    in1.on()
    in2.off()
    pump_speed.duty(int(max(0, min(1023, speed))))

def pump_to_algae(speed):
    in1.off()
    in2.on()
    pump_speed.duty(int(max(0, min(1023, speed))))

def pump_stop():
    in1.off()
    in2.off()
    pump_speed.duty(0)

# ----- Measure OD Value -----
PUMP_PRIME_TIME = 1   # tune this to your tube length
PUMP_DUTY      = 100    # tune this to your setup

def measure_OD():
    pump_to_mussel(PUMP_DUTY)
    utime.sleep(PUMP_PRIME_TIME)  # just enough to reach sensor
    
    led.on()
    utime.sleep(1)
    _, _, _, sample_reading = OD_sensor.read(True) 
    utime.sleep(1)
    led.off()
    
    pump_stop()

    return math.log10(CLEAR_OD_READING  / sample_reading) if sample_reading else None

# ------ Mussel Feeding ------
def od_to_algae_concentration(od):
    # cells/mL in the algae feed water
    return max(0, OD_TO_CELLS_SLOPE * od + OD_TO_CELLS_INTERCEPT)

def pump_speed_from_od(feed_od):
    feed_conc = od_to_algae_concentration(feed_od)

    if feed_conc <= 0:
        return 0

    algae_needed_per_min = CLEARING_RATE_ML_MIN * TARGET_ALGAE_CONC
    flow_ml_min = algae_needed_per_min / feed_conc

    return flow_ml_min / PUMP_ML_MIN_PER_DUTY


# ----- Water Level Tracking -----
accumulated_flow_ml = 0.0  # positive = pumped to mussel, negative = pumped to algae

def water_tracker(speed, duration_s):
    global accumulated_flow_ml

    pump_to_mussel(speed)
    utime.sleep(duration_s)
    pump_stop()

    accumulated_flow_ml += speed * PUMP_ML_MIN_PER_DUTY * (duration_s / 60)

# ------- Water Level Equalizer -------
EQUALIZE_INTERVAL = 300  # every 5 minutes
last_equalize = utime.ticks_ms()

def equalize():
    global accumulated_flow_ml

    if accumulated_flow_ml <= 0:
        return  # nothing to equalize

    # calculate how long to run pump in reverse at a fixed speed
    EQUALIZE_DUTY = 200
    flow_per_min = EQUALIZE_DUTY * PUMP_ML_MIN_PER_DUTY
    duration_s = (accumulated_flow_ml / flow_per_min) * 60

    pump_to_algae(EQUALIZE_DUTY)
    utime.sleep(duration_s)
    pump_stop()

    accumulated_flow_ml = 0.0  # reset after equalization

# -------- Main Loop --------
while True:
    MQTT.check_messages(client)

    od_measured = measure_OD()

    if od_measured is not None:
        speed = pump_speed_from_od(od_measured)
        pump_to_mussel(speed)
        MQTT.publish(client, flow_rate, speed) # publish data to adaFruit
        MQTT.publish(client, od_feed, od_measured) # publish data to adaFruit
    else:
        pump_stop()

    # equalize periodically
    if utime.ticks_diff(utime.ticks_ms(), last_equalize) > EQUALIZE_INTERVAL * 1000:
        equalize()
        last_equalize = utime.ticks_ms()

    utime.sleep(60)  # measure every minute
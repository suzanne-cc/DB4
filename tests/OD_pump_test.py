from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
import utime
import math
from pin_configuration import OD_PUMP, SCL_PIN, SDA_PIN, LED_PIN
import display

# ---------- Pins ----------
pump = PWM(Pin(OD_PUMP), freq=1000)

i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=1000)
OD_sensor = TCS34725(i2c)
led = Pin(LED_PIN, Pin.OUT)

# ------ Variables ------
OD_TO_CELLS_SLOPE = 1.0e7
OD_TO_CELLS_INTERCEPT = 0.0
CLEARING_RATE_ML_SEC = 120.0
CLEAR_OD_READING = 1000
PUMP_ML_MIN_PER_DUTY = 0.05
INITIAL_CONCENTRATION = 10000
TARGET_ALGAE = 1.0e6

# ----- Measure OD Value -----
PUMP_PRIME_TIME = 1
PUMP_DUTY = 100

def measure_OD():
    pump.duty(PUMP_DUTY)
    utime.sleep(PUMP_PRIME_TIME)

    led.on()
    utime.sleep(1)
    _, _, sample_reading, _ = OD_sensor.read(True)
    utime.sleep(1)
    led.off()

    pump.duty(0)
    return math.log10(CLEAR_OD_READING / sample_reading) if sample_reading else None

# ------ Mussel Feeding ------
def od_to_algae_concentration(od):
    return max(0, OD_TO_CELLS_SLOPE * od + OD_TO_CELLS_INTERCEPT)

last_feed = utime.time()

def pump_speed_from_od(feed_od):
    global last_feed
    feed_conc = od_to_algae_concentration(feed_od)
    if feed_conc <= 0:
        return 0

    total_algae = INITIAL_CONCENTRATION - (CLEARING_RATE_ML_SEC * (utime.time() - last_feed))
    algae_needed_per_sec = TARGET_ALGAE - total_algae
    flow_ml_sec = algae_needed_per_sec / feed_conc
    speed = flow_ml_sec / PUMP_ML_MIN_PER_DUTY

    last_feed = utime.time()
    return int(max(0, min(1023, speed)))

# -------- Main Loop --------
start = utime.time()
display.init_display(i2c)

while True:
    od_measured = measure_OD()

    if od_measured is not None:
        speed = pump_speed_from_od(od_measured)
        pump.duty(speed)
        flow_ml_s = speed * PUMP_ML_MIN_PER_DUTY  # actual flow value
        display.show_OD_reading(od_measured, speed, flow_ml_s)
    else:
        pump.duty(0)

    utime.sleep(60)
from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
import utime
import math
from pin_configuration import OD_PUMP,SCL_PIN, SDA_PIN, LED_PIN
import display

# ---------- Pins ----------
i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=1000)
OD_sensor = TCS34725(i2c)

led = Pin(LED_PIN, Pin.OUT)

# ------ Variables to be Defined ------
OD_TO_CELLS_SLOPE = 1.0e7
OD_TO_CELLS_INTERCEPT = 0.0

CLEAR_OD_READING = 1000

# ----- Measure OD Value -----
def measure_OD():
    led.on()
    utime.sleep(1)
    
    _, _, _, sample_reading = OD_sensor.read(True)
    print("OD reading:", sample_reading)
    print("Raw clear:", sample_reading)
    print("Calculated OD:", od_measured)
    
    utime.sleep(1)
    led.off()

    return math.log10(CLEAR_OD_READING  / sample_reading) if sample_reading else None

# -------- Main Loop --------
display.init_display(i2c)

while True:
    od_measured = measure_OD()
    display.show_OD_reading(od_measured)

    utime.sleep(1)  # measure every 10 sec
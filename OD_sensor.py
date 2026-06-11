from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
from provided_code.i2c_test import color_rgb_bytes
import utime
import MQTT
import math

# ---------- Pins ----------
pump_pin = Pin(13, Pin.OUT)
pump = PWM(pump_pin, freq=1000)

i2c = I2C(scl=Pin(22), sda=Pin(23), freq=100000)
OD_sensor = TCS34725(i2c)

led = Pin(14, Pin.OUT)

# ----- Measure OD Value -----
def measure_OD(reference):
    led.on()
    utime.sleep(1)  # lets the LED stabilise
    _, _, _, sample_reading = OD_sensor.read(True) 
    utime.sleep(1)  # gives time for the readings
    led.off()

    if sample_reading == 0:
        print('Error: sensor reading is 0')
        return None

    OD = math.log10(reference / sample_reading)
    return OD


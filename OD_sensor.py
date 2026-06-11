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
PUMP_PRIME_TIME = 0.3   # tune this to your tube length
PUMP_DUTY      = 100    # tune this to your setup

def measure_OD(reference):
    pump.duty(PUMP_DUTY)
    utime.sleep(PUMP_PRIME_TIME)  # just enough to reach sensor
    
    led.on()
    utime.sleep(1)
    _, _, _, sample_reading = OD_sensor.read(True) 
    utime.sleep(1)
    led.off()
    
    pump.duty(0)
    return math.log10(reference / sample_reading) if sample_reading else None
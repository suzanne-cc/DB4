from machine import Pin, ADC, PWM, I2C
from provided_code.tcs34725 import TCS34725
import utime
from pin_configuration import OD_PUMP, SCL_PIN, SDA_PIN, LED_PIN
from variables import *

# ---------- Pins ----------
pump = Pin(OD_PUMP, Pin.OUT)
pump.value(1)

i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=1000)
OD_sensor = TCS34725(i2c)
led = Pin(LED_PIN, Pin.OUT)

# ----- Measure OD Value -----
def measure_OD():
    print("measure start")
    pump.on()

    led.on()
    utime.sleep(1)
    _, _, sample_reading, _ = OD_sensor.read(True)
    utime.sleep(1)
    led.off()

    pump.off()
    
    print("measure end")
    return sample_reading

# ----- Main Loop -----

od_measured = measure_OD()
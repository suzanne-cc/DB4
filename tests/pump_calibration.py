from machine import Pin, ADC, PWM
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN

# ---------- Pins ----------
pump = PWM(Pin(TEMP_PUMP), freq=1000)
temp_sens = init_temp_sensor(THERMISTOR_PIN)

# ----- Temperature Regulation -----
speed = 10

pump_duty = int(1023 * (speed / 100))
pump.duty(pump_duty)
print(f"speed: {speed}")
utime.sleep(10) # 10 sec

pump.duty(0)
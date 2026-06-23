from machine import Pin, PWM
import utime
from pin_configuration import OD_PUMP

# ---------- Pins ----------
pump = PWM(Pin(OD_PUMP), freq=1000)

# ----- Temperature Regulation -----
speed = 10

pump_duty = int(1023 * (speed / 100))

pump.duty(pump_duty)
print(f"speed: {speed}")
utime.sleep(10) # 10 sec
pump.duty(0)

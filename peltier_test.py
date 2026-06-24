from machine import Pin
import utime

from pin_configuration import FAN_PIN, PELTIER_PIN

fan = Pin(FAN_PIN, Pin.OUT)
peltier = Pin(PELTIER_PIN, Pin.OUT)

fan.off()
peltier.off()

try:
    print("Fan ON")
    fan.on()
    utime.sleep(2)

    print("Peltier ON")
    peltier.on()
    utime.sleep(5)

    print("Peltier OFF")
    peltier.off()

    print("Fan cooling down")
    utime.sleep(5)

    fan.off()
    print("Fan OFF")

except:
    peltier.off()
    fan.off()
    raise
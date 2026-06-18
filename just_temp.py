from provided_code.read_temp import init_temp_sensor, read_temp
from pin_configuration import THERMISTOR_PIN
import utime

print("Starting temperature test")

temp_sens = init_temp_sensor(THERMISTOR_PIN)

try:
    while True:
        temp = read_temp(temp_sens)

        print("Temperature: {:.2f} C".format(temp))

        utime.sleep(2)

except KeyboardInterrupt:
    print("Temperature test stopped")
    
import utime

from display import init_display, show_thermistor_status, show_error
from thermistor import read_temperature


init_display()


while True:
    try:
        raw_adc, resistance, temp_c = read_temperature()

        print("Raw ADC:", raw_adc)
        print("Resistance:", resistance, "ohms")
        print("Temperature:", temp_c, "C")
        print()

        show_thermistor_status(raw_adc, temp_c)

    except Exception as error:
        print("Error:", error)
        show_error("Read failed")

    utime.sleep(1)

from machine import Pin, ADC, I2C
import utime
import math
import ssd1306


# OLED settings
OLED_WIDTH = 128
OLED_HEIGHT = 64
OLED_ADDR = 0x3C
SDA_PIN = 21
SCL_PIN = 22

# Thermistor settings
THERMISTOR_PIN = 34
NOMINAL_RESISTANCE = 10000
SERIES_RESISTOR = 10000
NOMINAL_TEMP = 25
BETA = 3950
ADC_MAX = 4095


# Start OLED
i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=400000)
oled = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)

# Start thermistor ADC
adc = ADC(Pin(THERMISTOR_PIN))
adc.atten(ADC.ATTN_11DB)
adc.width(ADC.WIDTH_12BIT)


def get_temperature():
    raw = adc.read()

    # Keep the math safe if the ADC reads exactly 0 or 4095.
    if raw <= 0:
        raw = 1
    if raw >= ADC_MAX:
        raw = ADC_MAX - 1

    # Wiring: 3V3 -> 10k resistor -> ADC point -> thermistor -> GND
    resistance = SERIES_RESISTOR * raw / (ADC_MAX - raw)

    temp_k = 1 / (
        (1 / (NOMINAL_TEMP + 273.15))
        + (1 / BETA) * math.log(resistance / NOMINAL_RESISTANCE)
    )
    temp_c = temp_k - 273.15

    return raw, resistance, temp_c


while True:
    raw_adc, resistance, temp_c = get_temperature()

    print("Raw ADC:", raw_adc)
    print("Resistance:", resistance, "ohms")
    print("Temperature:", temp_c, "C")
    print()

    oled.fill(0)
    oled.text("DB4 BIOREACTOR", 0, 0)
    oled.text("Thermistor test", 0, 12)
    oled.text("Raw: {}".format(raw_adc), 0, 28)
    oled.text("Temp: {:.1f} C".format(temp_c), 0, 42)
    oled.text("Touch sensor :)", 0, 56)
    oled.show()

    utime.sleep(1)

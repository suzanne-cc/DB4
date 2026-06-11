from machine import Pin, ADC
import math

from config import (
    THERMISTOR_PIN,
    NOMINAL_RESISTANCE,
    SERIES_RESISTOR,
    NOMINAL_TEMP,
    BETA,
    ADC_MAX,
)


# Start thermistor ADC on GPIO34.
adc = ADC(Pin(THERMISTOR_PIN))
adc.atten(ADC.ATTN_11DB)
adc.width(ADC.WIDTH_12BIT)


def read_temperature():
    raw = adc.read()

    # Keep the math safe if the ADC reads exactly 0 or 4095.
    if raw <= 0:
        raw = 1
    if raw >= ADC_MAX:
        raw = ADC_MAX - 1

    # Wiring: 3V3 -> 10k resistor -> ADC point -> thermistor -> GND
    resistance = SERIES_RESISTOR * raw / (ADC_MAX - raw)

    # Beta equation.
    temp_k = 1 / (
        (1 / (NOMINAL_TEMP + 273.15))
        + (1 / BETA) * math.log(resistance / NOMINAL_RESISTANCE)
    )
    temp_c = temp_k - 273.15

    return raw, resistance, temp_c

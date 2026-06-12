from machine import Pin, ADC, PWM
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN
import display

# ---------- Pins ----------
pump_pin = Pin(TEMP_PUMP, Pin.OUT)
pump = PWM(pump_pin, freq=1000)
temp_sens = init_temp_sensor(THERMISTOR_PIN)

# ------ Update Target Temperature -------
TARGET_TEMP = 17.0  # default until updated from dashboard
Kp, Ki, Kd = 10.0, 0.1, 1.0

# ---------- PID ----------
integral = 0
prev_error = 0
prev_time = utime.ticks_ms()

def PID(current_temp):
    global integral, prev_error, prev_time, Kp, Ki, Kd

    time_now = utime.ticks_ms()
    dt = utime.ticks_diff(time_now, prev_time) / 1000.0 # difference between prev PID call and new one (in seconds)

    if dt <= 0: # prevent division by zero
        dt = 0.001

    error = current_temp - TARGET_TEMP

    integral += error * dt # how long you've been off
    integral = max(-100, min(100, integral))  # prevents windup
    derivative = (error - prev_error) / dt

    P = Kp * error # how far off right now
    I = Ki * integral # how long you've been off
    D = Kd * derivative # how fast it's changing
    
    prev_error, prev_time = error, time_now

    output = P + I + D
    return output

# ----- Temperature Regulation -----
display.init_display()

while True:

    raw_adc = temp_sens.read()
    temp = read_temp(temp_sens)

    display.show_thermistor_status(raw_adc, temp)

    utime.sleep(10)
from machine import Pin, ADC, PWM
import utime
from provided_code.read_temp import init_temp_sensor, read_temp

# ---------- Pins ----------
pump_pin = Pin(12, Pin.OUT)
pump = PWM(pump_pin, freq=1000)
temp_sens = init_temp_sensor(32)

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
while True:
    temp = read_temp(temp_sens) # reading temperature

    pump_speed = PID(temp) # control speed of cooler
    pump.duty(int(max(0, min(1023, pump_speed))))

    utime.sleep(10) # 10sec delay
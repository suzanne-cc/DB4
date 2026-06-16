from machine import Pin, ADC, PWM, I2C
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN, SCL_PIN, SDA_PIN
import display

# ---------- Pins ----------
i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=100000)
pump = PWM(Pin(TEMP_PUMP), freq=1000)
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

# ----- Pump Flow Rate ----
def flow_rate(duty):
    duty = (duty/1023) * 100
    ml_per_sec = 0.161 * duty - 3.553
    return ml_per_sec


# ----- Temperature Regulation -----
display.init_display(i2c)

while True:
    temp = read_temp(temp_sens)
    pump_speed = PID(temp)
    pump_duty = int(max(0, min(1023, pump_speed)))
    pump.duty(pump_duty)
    
    rate = flow_rate(pump_duty)

    display.show_thermistor_status(temp, pump_speed, pump_duty, rate)

    utime.sleep(10)
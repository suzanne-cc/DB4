from machine import Pin, ADC, PWM
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
import MQTT
from pin_configuration import TEMP_PUMP, TEMP_PUMP_2, THERMISTOR_PIN
import display

# ---------- Pins ----------
pump = PWM(Pin(TEMP_PUMP), freq=1000)  # forward — connected to IA
pump_pin2 = Pin(TEMP_PUMP_2, Pin.OUT)        # tied low — connected to IB
pump_pin2.off()                              # always off for one way

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
    temp = read_temp(temp_sens) # reading temperature

    pump_speed = PID(temp) # raw PID output
    pump_duty = int(max(0, min(1023, pump_speed))) # actual pump command

    pump.duty(pump_duty)
    display.show_thermistor_status(temp, pump_speed, pump_duty)

    utime.sleep(10) # 10sec delay
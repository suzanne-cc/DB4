from machine import Pin, ADC, PWM
import utime
from read_temp import init_temp_sensor, read_temp
import MQTT

# ---------- Pins ----------
pump_pin = Pin(12, Pin.OUT)
pump = PWM(pump_pin, freq=1000)
temp_sens = init_temp_sensor(32)

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

feed_temp = MQTT.make_feed(b'temperature')
feed_pid  = MQTT.make_feed(b'PID-output')

# ---------- PID ----------
TARGET_TEMP = 17.0 # desired temperature in Celsius

Kp = 10.0 # Proportional gain
Ki = 0.1 # Integral gain
Kd = 1.0 # Derivative gain

integral = 0
prev_error = 0
prev_time = utime.ticks_ms()

def PID(current_temp):
    global integral, prev_error, prev_time

    time_now = utime.ticks_ms()
    dt = utime.ticks_diff(time_now, prev_time) / 1000.0 # difference between prev PID call and new one (in seconds)

    if dt <= 0: # prevent division by zero
        dt = 0.001

    error = current_temp - TARGET_TEMP

    integral += error * dt
    integral = max(-100, min(100, integral))  # prevent windup
    derivative = (error - prev_error) / dt

    P = Kp * error
    I = Ki * integral
    D = Kd * derivative
    
    prev_error, prev_time = error, time_now

    output = P + I + D
    return output


# ----- Temperature Regulation -----
while True:
    try:
        temp = read_temp(temp_sens) # reading temperature

        pump_speed = PID(temp) # control speed of cooler
        pump.duty(int(max(0, min(1023, pump_speed))))

        MQTT.publish(client, feed_temp, temp) # publish temperature data to adaFruit
        MQTT.publish(client, feed_pid, pump_speed) # publish PID data to adaFruit

        utime.sleep(10) # 10sec delay

    except KeyboardInterrupt:
        print('Ctrl-C pressed...exiting')
        client.disconnect()
        break
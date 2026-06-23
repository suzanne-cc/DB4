from machine import Pin, ADC, PWM, I2C
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
import MQTT
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN, SCL_PIN, SDA_PIN
import display
import storage
from variables import *

# ---------- Pins ----------
i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=100000)
pump_pin = Pin(TEMP_PUMP, Pin.OUT)
pump = PWM(pump_pin, freq=1000)
temp_sens = init_temp_sensor(THERMISTOR_PIN)

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

feed_temp = MQTT.make_feed(b'temperature-sensor.temperature')
feed_pid  = MQTT.make_feed(b'temperature-sensor.pid-output')

# ------ Update Target Temperature -------
feed_target_temp = MQTT.make_feed(b'subscribed-data.target-temp')
feed_kp          = MQTT.make_feed(b'subscribed-data.kp-gain')
feed_ki          = MQTT.make_feed(b'subscribed-data.ki-gain')
feed_kd          = MQTT.make_feed(b'subscribed-data.kd-gain')

def on_message(topic, msg):
    global TARGET_TEMP, Kp, Ki, Kd
    try:
        value = float(msg.decode('utf-8'))

        if topic == feed_target_temp:
            TARGET_TEMP = value
            integral = 0  # reset integral so old accumulation doesn't carry over
            print('Target temp updated to: {}'.format(value))
        elif topic == feed_kp:
            Kp = value
            print('Kp updated to: {}'.format(value))
        elif topic == feed_ki:
            Ki = value
            print('Ki updated to: {}'.format(value))
        elif topic == feed_kd:
            Kd = value
            print('Kd updated to: {}'.format(value))
        else:
            print('Unknown topic: {}'.format(topic))

    except ValueError:
        print('Invalid value received: {}'.format(msg))

MQTT.subscribe(client, feed_target_temp, on_message)
MQTT.subscribe(client, feed_kp, on_message)
MQTT.subscribe(client, feed_ki, on_message)
MQTT.subscribe(client, feed_kd, on_message)

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
def flow_rate(duty, time):
    duty = (duty/1023) * 100
    ml_per_sec = 0.161 * duty - 3.553
    return ml_per_sec * time

# ----- Temperature Regulation -----
storage.init_csv("Temperature_Regulator", ["Time [s]", "Measured Temperature [C]", "PID"])
start = utime.time()

while True:
    MQTT.check_messages(client)  # checks for any received updates
    temp = read_temp(temp_sens) # reading temperature
    display.update_temp(temp)

    pid = PID(temp) # control speed of cooler
    pump.duty(int(max(0, min(1023, pid))))
    display.update_PID(pid)

    MQTT.publish(client, feed_temp, temp) # publish temperature data to adaFruit
    MQTT.publish(client, feed_pid, pid) # publish PID data to adaFruit
    storage.store_data(utime.time() - start, temp, pid)

    utime.sleep(10) # 10sec delay
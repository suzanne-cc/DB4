from machine import Pin, ADC, PWM
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
import MQTT
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN

# ---------- Pins ----------
pump_pin = Pin(TEMP_PUMP, Pin.OUT)
pump = PWM(pump_pin, freq=1000)
temp_sens = init_temp_sensor(THERMISTOR_PIN)

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

feed_temp = MQTT.make_feed(b'temperature')
feed_pid  = MQTT.make_feed(b'PID-output')

# ------ Update Target Temperature -------
TARGET_TEMP = 17.0  # default until updated from dashboard
Kp, Ki, Kd = 10.0, 0.1, 1.0

feed_target_temp = MQTT.make_feed(b'target-temp')
feed_kp          = MQTT.make_feed(b'kp-gain')
feed_ki          = MQTT.make_feed(b'ki-gain')
feed_kd          = MQTT.make_feed(b'kd-gain')

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


# ----- Temperature Regulation -----
while True:
    try:
        MQTT.check_messages(client)  # checks for any received updates
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
from machine import Pin, ADC, PWM, I2C
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
import MQTT
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN, SCL_PIN, SDA_PIN, FAN_PIN, PELTIER_PIN
import display
import storage
from variables import *

# ---------- Pins ----------
i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=100000)
temp_sens = init_temp_sensor(THERMISTOR_PIN)

fan = Pin(FAN_PIN, Pin.OUT)
peltier = Pin(PELTIER_PIN, Pin.OUT)
pump = Pin(TEMP_PUMP, Pin.OUT)

# ----- Peltier Element -----
def peltier_low():
    peltier.off()

def peltier_high():
    peltier.on()

# ----- Pump -----
def pump_on():
    pump.off()

def pump_off():
    pump.on()

fan.off()
pump_off()
peltier_low()

# ------- MQTT Setup -------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

feed_temp = MQTT.make_feed(b'temperature-sensor.temperature')
feed_pid  = MQTT.make_feed(b'temperature-sensor.pid-output')

feed_target_temp = MQTT.make_feed(b'subscribed-data.target-temp')
feed_kp          = MQTT.make_feed(b'subscribed-data.kp-gain')
feed_ki          = MQTT.make_feed(b'subscribed-data.ki-gain')
feed_kd          = MQTT.make_feed(b'subscribed-data.kd-gain')

def on_message(topic, msg):
    global TARGET_TEMP, Kp, Ki, Kd, integral
    try:
        value = float(msg.decode('utf-8'))

        if topic == feed_target_temp:
            TARGET_TEMP = value
            integral = 0
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
    dt = utime.ticks_diff(time_now, prev_time) / 1000.0
    if dt <= 0:
        dt = 0.001

    error = current_temp - TARGET_TEMP  # positive = too hot = need more cooling

    integral += error * dt
    integral = max(-100, min(100, integral))  # anti-windup
    derivative = (error - prev_error) / dt

    P = Kp * error
    I = Ki * integral
    D = Kd * derivative

    prev_error, prev_time = error, time_now

    output = P + I + D
    return max(0, min(100, output))  # clamped 0-100, used here for telemetry only


# ----- Cooling State -----
cooling_active = False
peltier_start_time = 0

storage.init_csv("Temperature_Regulator", ["Time [s]", "Measured Temperature [C]"])
start = utime.time()

PUBLISH_INTERVAL_MS = 10000
last_publish_time = utime.ticks_ms()

while True:
    MQTT.check_messages(client)

    # --- measure temperature ---
    temps = []
    for _ in range(5):
        temps.append(read_temp(temp_sens))
        utime.sleep(0.1)
    temperature = sum(temps) / 5
    display.update_temp(temperature)

    # --- PID computed for logging/telemetry, doesn't drive switching ---
    duty_pct = PID(temperature)
    display.update_PID(duty_pct)

    if not cooling_active:

        if temperature >= TARGET_TEMP + HYSTERESIS:

            pump_on()
            peltier_high()

            cooling_active = True
            peltier_start_time = utime.ticks_ms()

            print("Cooling switched ON")

    else:

        current_time = utime.ticks_ms()

        peltier_on_time = utime.ticks_diff(
            current_time,
            peltier_start_time
        )

        minimum_time_reached = (
            peltier_on_time >= MIN_PELTIER_ON_TIME_MS
        )

        if temperature <= TARGET_TEMP and minimum_time_reached:

            peltier_low()
            pump_off()

            cooling_active = False

            print("Cooling switched OFF")

    # --- publish to Adafruit IO only every PUBLISH_INTERVAL_MS ---
    now = utime.ticks_ms()
    if utime.ticks_diff(now, last_publish_time) >= PUBLISH_INTERVAL_MS:
        MQTT.publish(client, feed_temp, temperature)
        MQTT.publish(client, feed_pid, duty_pct)
        storage.store_data(utime.time() - start, temperature)
        last_publish_time = now

    utime.sleep(1)  # control loop stays responsive; publishing is throttled separately
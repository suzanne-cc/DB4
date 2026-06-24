import asyncio
from machine import Pin, PWM
import utime
from provided_code.read_temp import init_temp_sensor, read_temp
import MQTT
from pin_configuration import TEMP_PUMP, THERMISTOR_PIN, FAN_PIN, PELTIER_PIN
import display
import storage
from variables import *

# ---------- Pins ----------
temp_sens = init_temp_sensor(THERMISTOR_PIN)

fan = Pin(FAN_PIN, Pin.OUT)
peltier = Pin(PELTIER_PIN, Pin.OUT)
pump_pin = Pin(TEMP_PUMP, Pin.OUT)
pump = PWM(pump_pin, freq=1000)

def peltier_low():
    peltier.off()

def peltier_high():
    peltier.on()

# ----- Initial States -----
fan.off()
pump.duty(0)
peltier_low()

# ------- MQTT feeds (set by main.py after MQTT connects) -------
feed_temp = MQTT.make_feed(b'temperature-sensor.temperature')
feed_pid  = MQTT.make_feed(b'temperature-sensor.pid-output')

feed_target_temp = MQTT.make_feed(b'subscribed-data.target-temp')
feed_kp          = MQTT.make_feed(b'subscribed-data.kp-gain')
feed_ki          = MQTT.make_feed(b'subscribed-data.ki-gain')
feed_kd          = MQTT.make_feed(b'subscribed-data.kd-gain')

# Called by the master callback in main.py
def handle_mqtt(topic, msg):
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
    except ValueError:
        print('Invalid value received: {}'.format(msg))

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

    error = current_temp - TARGET_TEMP
    integral += error * dt
    integral = max(-100, min(100, integral))
    derivative = (error - prev_error) / dt

    P = Kp * error
    I = Ki * integral
    D = Kd * derivative

    prev_error, prev_time = error, time_now
    return P + I + D


# ============================================================
# ASYNC TASK
# ============================================================
async def cooling_task(i2c, client):
    cooling_active = False
    peltier_start_time = 0

    storage.init_csv("Temperature_Regulator",
                     ["Time [s]", "Measured Temperature [C]"])
    start = utime.time()

    PUBLISH_INTERVAL_MS = 10000
    last_publish_time = utime.ticks_ms()

    while True:
        # --- measure temperature (averaged over 5 reads) ---
        temps = []
        for _ in range(5):
            temps.append(read_temp(temp_sens))
            await asyncio.sleep_ms(100)
        temperature = sum(temps) / 5
        display.update_temp(temperature)

        duty = PID(temperature)
        display.update_PID(duty)

        # --- hysteresis cooling control ---
        if not cooling_active:
            if temperature >= TARGET_TEMP + HYSTERESIS:
                pump.duty(int(max(0, min(1023, duty))))
                peltier_high()
                cooling_active = True
                peltier_start_time = utime.ticks_ms()
                print("Cooling switched ON")
        else:
            peltier_on_time = utime.ticks_diff(utime.ticks_ms(),
                                               peltier_start_time)
            minimum_time_reached = peltier_on_time >= MIN_PELTIER_ON_TIME_MS
            if temperature <= TARGET_TEMP and minimum_time_reached:
                peltier_low()
                pump.duty(0)
                cooling_active = False
                print("Cooling switched OFF")

        # --- publish (throttled) ---
        now = utime.ticks_ms()
        if utime.ticks_diff(now, last_publish_time) >= PUBLISH_INTERVAL_MS:
            MQTT.publish(client, feed_temp, temperature)
            MQTT.publish(client, feed_pid, duty)
            storage.store_data(utime.time() - start, temperature)
            last_publish_time = now

        await asyncio.sleep(1)
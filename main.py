import asyncio
from machine import Pin, I2C

import MQTT
import display
from pin_configuration import SCL_PIN, SDA_PIN

import cooling_control
import OD_sensor
from cooling_control import cooling_task
from OD_sensor import od_task

# ---------- Shared hardware ----------
i2c = I2C(1, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=100000)
display.init_display(i2c)

# ---------- MQTT (ONE connection, shared by both tasks) ----------
MQTT.connect_wifi()
client = MQTT.connect_mqtt()

# Master callback dispatches to both modules.
# Each module's handler ignores topics it doesn't own.
def master_callback(topic, msg):
    cooling_control.handle_mqtt(topic, msg)
    OD_sensor.handle_mqtt(topic, msg)

client.set_callback(master_callback)
client.subscribe(cooling_control.feed_target_temp)
client.subscribe(cooling_control.feed_kp)
client.subscribe(cooling_control.feed_ki)
client.subscribe(cooling_control.feed_kd)
client.subscribe(OD_sensor.feed_target_algae)

# ---------- MQTT polling task ----------
async def mqtt_poll_task():
    while True:
        try:
            client.check_msg()
        except Exception as e:
            print("MQTT check failed:", e)
        await asyncio.sleep(1)

# ---------- Main ----------
async def main():
    asyncio.create_task(mqtt_poll_task())
    asyncio.create_task(cooling_task(i2c, client))
    asyncio.create_task(od_task(i2c, client))
    while True:
        await asyncio.sleep(60)

asyncio.run(main())
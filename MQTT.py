import network
import time
from umqtt.robust import MQTTClient
import os
import sys

WIFI_SSID = 'suzanne'
WIFI_PASSWORD = 'suzanne1201'

ADAFRUIT_IO_URL = b'io.adafruit.com' 
ADAFRUIT_USERNAME = b'suzanne_cc'
ADAFRUIT_IO_KEY = b'aio_MBut59NFkWgutoighj9UO2unalOg'

def connect_wifi():
    # turn off the WiFi Access Point
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)

    # connect the device to the WiFi network
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    wifi.connect(WIFI_SSID, WIFI_PASSWORD)

    # wait until the device is connected to the WiFi network
    MAX_ATTEMPTS = 20
    attempt_count = 0
    while not wifi.isconnected() and attempt_count < MAX_ATTEMPTS:
        attempt_count += 1
        time.sleep(1)

    if attempt_count == MAX_ATTEMPTS:
        print('could not connect to the WiFi network')
        sys.exit()

def connect_mqtt():
    # create a random MQTT clientID 
    random_num = int.from_bytes(os.urandom(3), 'little')
    mqtt_client_id = bytes('client_' + str(random_num), 'utf-8')

    client = MQTTClient(client_id=mqtt_client_id,
                        server=ADAFRUIT_IO_URL,
                        user=ADAFRUIT_USERNAME,
                        password=ADAFRUIT_IO_KEY,
                        ssl=False)
    try:
        client.connect()
        return client
    except Exception as e:
        print('could not connect to MQTT server {}{}'.format(type(e).__name__, e))
        sys.exit()

def make_feed(feedname):
    return bytes('{:s}/feeds/{:s}'.format(ADAFRUIT_USERNAME, feedname), 'utf-8')

def publish(client, feed, value):
    try:
        client.publish(feed, bytes(str(round(value, 2)), 'utf-8'), qos=0)
    except Exception as e:
        print('Publish failed: {}{}'.format(type(e).__name__, e))

def subscribe(client, feed, callback):
    client.set_callback(callback)
    client.subscribe(feed)

def check_messages(client):
    client.check_msg()  # checks if any new message has arrived
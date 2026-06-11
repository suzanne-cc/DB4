"""Small MQTT helper for the DB4 bioreactor.

This file keeps all WiFi and Adafruit IO details in one place so the main
controller can focus on sensors, pumps, cooling, and feeding.
"""

import network  # Load the ESP32 WiFi module.
import os  # Load random bytes for a unique MQTT client name.
import time  # Load sleep functions for connection retries.
from umqtt.robust import MQTTClient  # Load the MicroPython MQTT client.


# Change this to the WiFi network name before uploading to the ESP32.
WIFI_SSID = "wifi_SSID"

# Change this to the WiFi password before uploading to the ESP32.
WIFI_PASSWORD = "password"

# Keep the Adafruit IO server as bytes because the MQTT library accepts bytes.
ADAFRUIT_IO_URL = b"io.adafruit.com"

# Change this to your Adafruit IO username before uploading.
ADAFRUIT_USERNAME = "username"

# Change this to your Adafruit IO key before uploading.
ADAFRUIT_IO_KEY = "key"


def _to_bytes(value):
    """Convert text-like values to bytes for the MQTT library."""
    if isinstance(value, bytes):  # Leave bytes unchanged.
        return value

    return str(value).encode("utf-8")  # Encode strings/numbers as UTF-8 bytes.


def _to_text(value):
    """Convert bytes or text to normal text for building topic names."""
    if isinstance(value, bytes):  # Decode byte values when needed.
        return value.decode("utf-8")

    return str(value)  # Convert every other value to plain text.


def connect_wifi(max_attempts=20):
    """Connect the ESP32 to WiFi and return the station object."""
    ap_if = network.WLAN(network.AP_IF)  # Select the ESP32 access-point mode.
    ap_if.active(False)  # Turn off the ESP32 hotspot to save power/noise.

    wifi = network.WLAN(network.STA_IF)  # Select normal WiFi client mode.
    wifi.active(True)  # Turn on the WiFi radio.

    if not wifi.isconnected():  # Only reconnect if we are not already online.
        print("Connecting to WiFi...")  # Tell the serial monitor what is happening.
        wifi.connect(WIFI_SSID, WIFI_PASSWORD)  # Start the WiFi login.

    attempt_count = 0  # Count how many seconds we have waited.

    while not wifi.isconnected() and attempt_count < max_attempts:  # Wait with a limit.
        attempt_count += 1  # Add one retry.
        time.sleep(1)  # Give the router one second to answer.

    if not wifi.isconnected():  # Check if all retries failed.
        print("WiFi not connected; controller will keep running locally.")  # Explain fallback.
        return None  # Return no WiFi so the main loop can continue safely.

    print("WiFi connected:", wifi.ifconfig())  # Print the IP details for debugging.
    return wifi  # Return the connected WiFi object.


def connect_mqtt():
    """Connect to Adafruit IO and return an MQTT client, or None if it fails."""
    random_num = int.from_bytes(os.urandom(3), "little")  # Make a random number.
    mqtt_client_id = _to_bytes("db4_bioreactor_" + str(random_num))  # Make a unique ID.

    client = MQTTClient(  # Create the MQTT client object.
        client_id=mqtt_client_id,  # Give the client its unique ID.
        server=ADAFRUIT_IO_URL,  # Tell it the Adafruit IO server.
        user=_to_bytes(ADAFRUIT_USERNAME),  # Send the Adafruit username.
        password=_to_bytes(ADAFRUIT_IO_KEY),  # Send the Adafruit IO key.
        ssl=False,  # Use plain MQTT because this MicroPython setup used port 1883.
    )

    try:  # Try the network connection because WiFi can be unreliable.
        client.connect()  # Open the MQTT connection.
        print("MQTT connected.")  # Confirm success in the serial monitor.
        return client  # Return the connected client.

    except Exception as error:  # Catch connection errors so control still runs.
        print("MQTT not connected:", type(error).__name__, error)  # Show the failure.
        return None  # Return no client so the main loop can skip publishing.


def make_feed(feedname):
    """Build an Adafruit IO feed topic like username/feeds/temperature."""
    username = _to_text(ADAFRUIT_USERNAME)  # Convert username to text.
    feed = _to_text(feedname)  # Convert the feed name to text.
    topic = "{}/feeds/{}".format(username, feed)  # Build the Adafruit topic.
    return _to_bytes(topic)  # Return bytes because MQTTClient expects bytes.


def publish(client, feed, value, decimals=2):
    """Publish one value and return True when it was sent."""
    if client is None:  # Skip publishing if MQTT is offline.
        return False

    try:  # Try publishing because WiFi can drop mid-run.
        if isinstance(value, float):  # Format floats cleanly for dashboards.
            payload = str(round(value, decimals))  # Round numeric sensor data.
        else:  # Keep strings, booleans, and integers readable.
            payload = str(value)  # Convert the value to text.

        client.publish(feed, _to_bytes(payload), qos=0)  # Send the payload to Adafruit IO.
        return True  # Report success.

    except Exception as error:  # Catch publish failures so hardware control continues.
        print("Publish failed:", type(error).__name__, error)  # Show the error.
        return False  # Report failure.


def subscribe(client, feed):
    """Subscribe to one Adafruit IO feed when MQTT is online."""
    if client is None:  # Skip subscribing if MQTT is offline.
        return False

    try:  # Try subscribing because network setup can fail.
        client.subscribe(feed)  # Ask Adafruit IO to send updates for this feed.
        return True  # Report success.

    except Exception as error:  # Catch subscribe failures.
        print("Subscribe failed:", type(error).__name__, error)  # Show the error.
        return False  # Report failure.

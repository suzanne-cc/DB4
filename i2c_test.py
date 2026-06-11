"""Quick I2C test for the OLED display and TCS34725 color sensor."""

from machine import I2C, Pin  # Load I2C and pin hardware support.
import time  # Load sleep for the repeating test loop.

import ssd1306  # Load the local OLED driver.
import tcs34725  # Load the local color sensor driver.


I2C_SCL_PIN = 22  # Use GPIO 22 for I2C clock.
I2C_SDA_PIN = 23  # Use GPIO 23 for I2C data.
OLED_WIDTH = 128  # Use a 128 pixel wide OLED.
OLED_HEIGHT = 64  # Use a 64 pixel tall OLED.


def color_rgb_bytes(color_raw):
    """Convert raw color sensor readings to 0-255 RGB values."""
    r, g, b, clear = color_raw  # Split red, green, blue, and clear channels.

    if clear == 0:  # Avoid divide-by-zero in darkness.
        return 0, 0, 0  # Return black.

    red = int(pow((int((r / clear) * 256) / 255), 2.5) * 255)  # Normalize red.
    green = int(pow((int((g / clear) * 256) / 255), 2.5) * 255)  # Normalize green.
    blue = int(pow((int((b / clear) * 256) / 255), 2.5) * 255)  # Normalize blue.
    red = min(255, red)  # Clamp red to one byte.
    green = min(255, green)  # Clamp green to one byte.
    blue = min(255, blue)  # Clamp blue to one byte.
    return red, green, blue  # Return RGB bytes.


i2c = I2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)  # Create the I2C bus.
oled = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)  # Create the OLED display.
sensor = tcs34725.TCS34725(i2c)  # Create the RGB sensor.
sensor.integration_time(50)  # Use a stable 50 ms color integration.
sensor.gain(16)  # Use medium gain.

while True:  # Repeat the test forever.
    raw = sensor.read(True)  # Read raw color channels.
    r, g, b = color_rgb_bytes(raw)  # Convert raw values to RGB bytes.
    _, _, _, clear = raw  # Read the clear channel for brightness.

    oled.fill(0)  # Clear the OLED buffer.
    oled.text("I2C test", 0, 0)  # Show test title.
    oled.text("R: {}".format(r), 0, 12)  # Show red value.
    oled.text("G: {}".format(g), 0, 24)  # Show green value.
    oled.text("B: {}".format(b), 0, 36)  # Show blue value.
    oled.text("C: {}".format(clear), 0, 48)  # Show clear value.
    oled.show()  # Push the buffer to the screen.

    print(">r:{} g:{} b:{} clear:{}<".format(r, g, b, clear))  # Print values to serial.
    time.sleep(1)  # Wait one second before the next sample.

"""Small hardware smoke tests for the DB4 ESP32/Huzzah setup.

Run this file directly to scan I2C and draw a smiley on the OLED. You can also
import it in the MicroPython REPL and call the individual test functions.
"""


I2C_SCL_PIN = 22  # Use GPIO 22 as the default I2C clock pin.
I2C_SDA_PIN = 23  # Use GPIO 23 as the default I2C data pin.
OLED_WIDTH = 128  # Use a 128 pixel wide SSD1306 OLED.
OLED_HEIGHT = 64  # Use a 64 pixel tall SSD1306 OLED.
OLED_ADDR = 0x3C  # Use the common SSD1306 I2C address.
TEMP_SENSOR_PIN = 32  # Use the same thermistor pin as the main controller.
ONBOARD_LED_PIN = 13  # Common Feather/Huzzah LED pin; change if your board differs.


def make_i2c(scl_pin=I2C_SCL_PIN, sda_pin=I2C_SDA_PIN):
    """Create the shared I2C bus."""
    from machine import I2C, Pin  # Load I2C and pin hardware support.

    return I2C(scl=Pin(scl_pin), sda=Pin(sda_pin), freq=100000)  # Create and return I2C.


def i2c_scan():
    """Print all I2C addresses found on the bus."""
    i2c = make_i2c()  # Create the I2C bus.
    devices = i2c.scan()  # Ask the bus which devices answered.
    addresses = [hex(device) for device in devices]  # Convert addresses to readable hex.
    print("I2C devices found:", addresses)  # Print the list to the serial monitor.
    return devices  # Return the raw numeric addresses.


def _plot_circle_pixels(oled, cx, cy, x, y, color):
    """Plot the eight matching points of a circle."""
    oled.pixel(cx + x, cy + y, color)  # Draw lower-right point.
    oled.pixel(cx - x, cy + y, color)  # Draw lower-left point.
    oled.pixel(cx + x, cy - y, color)  # Draw upper-right point.
    oled.pixel(cx - x, cy - y, color)  # Draw upper-left point.
    oled.pixel(cx + y, cy + x, color)  # Draw lower-right swapped point.
    oled.pixel(cx - y, cy + x, color)  # Draw lower-left swapped point.
    oled.pixel(cx + y, cy - x, color)  # Draw upper-right swapped point.
    oled.pixel(cx - y, cy - x, color)  # Draw upper-left swapped point.


def draw_circle(oled, cx, cy, radius, color=1):
    """Draw a simple circle outline."""
    x = 0  # Start at the side of the circle.
    y = radius  # Start at the top of the circle.
    decision = 3 - 2 * radius  # Start the midpoint circle decision value.

    while y >= x:  # Continue until the octants meet.
        _plot_circle_pixels(oled, cx, cy, x, y, color)  # Plot all symmetric points.
        x += 1  # Move one pixel sideways.

        if decision > 0:  # Check whether the curve needs to move inward.
            y -= 1  # Move one pixel inward.
            decision += 4 * (x - y) + 10  # Update decision after moving inward.
        else:  # Keep the same vertical radius for this step.
            decision += 4 * x + 6  # Update decision for the next point.


def fill_square(oled, x, y, size, color=1):
    """Draw a small filled square."""
    for px in range(x, x + size):  # Walk through each x position.
        for py in range(y, y + size):  # Walk through each y position.
            oled.pixel(px, py, color)  # Turn the pixel on or off.


def oled_smiley(seconds=10):
    """Draw a smiley face on the OLED display."""
    import utime  # Load sleep for keeping the picture visible.
    import ssd1306  # Load the local OLED driver.

    i2c = make_i2c()  # Create the I2C bus.
    oled = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)  # Create OLED.

    oled.fill(0)  # Clear the display.
    oled.text("DB4 OLED OK", 16, 0)  # Write a small success label.
    draw_circle(oled, 64, 34, 22)  # Draw the face outline.
    fill_square(oled, 54, 26, 4)  # Draw the left eye.
    fill_square(oled, 72, 26, 4)  # Draw the right eye.

    for x in range(-15, 16):  # Walk across the mouth width.
        y = 44 - (x * x) // 80  # Make a smile curve.
        oled.pixel(64 + x, y, 1)  # Draw one mouth pixel.
        oled.pixel(64 + x, y + 1, 1)  # Draw a second pixel to thicken the mouth.

    oled.text("smile test", 24, 56)  # Label the test at the bottom.
    oled.show()  # Send the buffer to the OLED.
    print("OLED smiley shown for", seconds, "seconds.")  # Print success.
    utime.sleep(seconds)  # Keep the smiley visible.
    return True  # Report success to the REPL.


def blink_led(pin_no=ONBOARD_LED_PIN, times=6, delay_ms=250):
    """Blink one GPIO pin as a simple output test."""
    from machine import Pin  # Load GPIO pin support.
    import utime  # Load timing helpers.

    led = Pin(pin_no, Pin.OUT)  # Create the output pin.

    for _ in range(times):  # Repeat the blink pattern.
        led.value(1)  # Turn the pin on.
        utime.sleep_ms(delay_ms)  # Wait while on.
        led.value(0)  # Turn the pin off.
        utime.sleep_ms(delay_ms)  # Wait while off.

    print("Blink test finished on pin", pin_no)  # Print completion.
    return True  # Report success to the REPL.


def thermistor_once(pin_no=TEMP_SENSOR_PIN):
    """Read the thermistor once and print the result."""
    from read_temp import init_temp_sensor, read_temp_details  # Load temperature helpers.

    sensor = init_temp_sensor(pin_no)  # Create the ADC thermistor reader.
    details = read_temp_details(sensor, debug=True)  # Read temperature and debug values.
    print("Temperature C:", details["temperature"])  # Print the Celsius result.
    return details  # Return all measured values.


def color_sensor_once():
    """Read the TCS34725 color sensor once and print raw channels."""
    import tcs34725  # Load the local color sensor driver.

    i2c = make_i2c()  # Create the I2C bus.
    sensor = tcs34725.TCS34725(i2c)  # Create the color sensor.
    sensor.integration_time(50)  # Use a stable 50 ms integration time.
    sensor.gain(16)  # Use medium gain.
    raw = sensor.read(True)  # Read raw red, green, blue, and clear channels.
    print("TCS34725 raw R,G,B,C:", raw)  # Print the raw reading.
    return raw  # Return the raw tuple.


def run_basic_tests():
    """Run the safest basic tests: I2C scan and OLED smiley."""
    devices = i2c_scan()  # Print detected I2C devices.

    if OLED_ADDR not in devices:  # Check whether the OLED address answered.
        print("OLED address 0x3c was not found; check SDA/SCL/power.")  # Explain issue.

    oled_smiley()  # Draw the smiley test.
    return devices  # Return the I2C scan result.


if __name__ == "__main__":  # Run this block only when the file is launched directly.
    run_basic_tests()  # Run the default safe tests.

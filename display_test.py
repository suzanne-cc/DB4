from machine import I2C, Pin
import ssd1306


SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 400000

OLED_WIDTH = 128
OLED_HEIGHT = 64
OLED_ADDR = 0x3C


i2c = I2C(
    0,
    sda=Pin(SDA_PIN),
    scl=Pin(SCL_PIN),
    freq=I2C_FREQ,
)

print("I2C devices found:", [hex(device) for device in i2c.scan()])

oled = ssd1306.SSD1306_I2C(
    OLED_WIDTH,
    OLED_HEIGHT,
    i2c,
    addr=OLED_ADDR,
)

oled.fill(0)
oled.text("melloll101", 0, 0)
oled.text("Status:", 0, 18)
oled.text("Connected OK", 0, 30)
oled.text("ESP32 running", 0, 44)
oled.text(":)", 0, 56)
oled.show()

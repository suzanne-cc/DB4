from machine import Pin, I2C
import provided_code.ssd1306

from pin_configuration import OLED_WIDTH, OLED_HEIGHT, OLED_ADDR, SDA_PIN, SCL_PIN

oled = None

def init_display():
    global oled

    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=400000)
    oled = provided_code.ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)

    oled.fill(0)
    oled.show()
    return oled

def show_thermistor_status(temp_c):
    oled.fill(0)
    #oled.text("DB4 PROJECT", 0, 0)
    #oled.text("Thermistor test", 0, 12)
    #oled.text("Raw: {}".format(raw_adc), 0, 28)
    oled.text("Temp: {:.1f} C".format(temp_c), 0, 42)
    oled.show()

def show_error(message):
    oled.fill(0)
    oled.text("DB4 BIOREACTOR", 0, 0)
    oled.text("ERROR", 0, 18)
    oled.text(message, 0, 34)
    oled.show()
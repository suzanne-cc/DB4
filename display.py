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

def show_thermistor_status(temp_c, speed, pump_duty, flow):
    oled.fill(0)
    oled.text("DB4 PROJECT", 0, 0)
    oled.text("Temp: {:.1f} C".format(temp_c), 0, 16)
    oled.text("PID: {:.1f}".format(speed), 0, 32)
    oled.text("Duty: {:.1f}".format(pump_duty), 0, 40)
    oled.test("Flow rate: {:.1f}".format(flow), 0, 52)
    oled.show()

def show_OD_reading(OD_measurment):
    oled.fill(0)
    oled.text("DB4 PROJECT", 0, 0)
    oled.text("OD: {:.1f} C".format(OD_measurment), 0, 16)
    oled.show()
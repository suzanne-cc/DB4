from machine import Pin, I2C
import provided_code.ssd1306
from pin_configuration import OLED_WIDTH, OLED_HEIGHT, OLED_ADDR, SDA_PIN, SCL_PIN

oled = None

def init_display(i2c):
    global oled
    oled = provided_code.ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)
    oled.fill(0)
    oled.show()
    return oled

last_temp = None
last_PID = None

def update_temp(temp):
    global last_temp
    last_temp = temp

def update_PID(PID):
    global last_PID
    last_PID = PID

def show_quick_overview(OD_measurement, Volume_Transfered, pump_duration):
    oled.fill(0)
    oled.text("DB4 PROJECT", 0, 0)
    
    if last_temp is not None:
        oled.text("Temp: {:.1f} C".format(last_temp), 0, 16)
    else:
        oled.text("Temp: --", 0, 16)

    if last_temp is not None:
        oled.text("PID: {:.1f}".format(last_PID), 0, 24)
    else:
        oled.text("PID: --", 0, 24)

    oled.text("OD: {:.1f}".format(OD_measurement), 0, 32)
    oled.text("Flow: {:.1f} ml".format(Volume_Transfered), 0, 40)
    oled.text("Pump: {:.1f} s".format(pump_duration), 0, 48)
    oled.show()

def show_thermistor_status(temp, pump_speed, pump_duty, rate):
    oled.fill(0)
    oled.text("Temp: {:.1f} C".format(temp), 0, 0)
    oled.text("PID: {:.1f}".format(pump_speed), 0, 16)
    oled.text("Duty: {}".format(pump_duty), 0, 32)
    oled.text("Flow: {:.1f}".format(rate), 0, 48)
    oled.show()
from machine import Pin, I2C
import provided_code.ssd1306
from pin_configuration import OLED_WIDTH, OLED_HEIGHT, OLED_ADDR, SDA_PIN, SCL_PIN

oled = None

# Cached state — display is rebuilt from these every redraw
last_temp = None
last_PID = None
last_OD = 0.0
last_volume = 0.0
last_pump = 0.0

def init_display(i2c):
    global oled
    oled = provided_code.ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)
    _redraw()
    return oled

def _redraw():
    if oled is None:
        return
    oled.fill(0)
    oled.text("DB4 PROJECT", 0, 0)

    if last_temp is not None:
        oled.text("Temp: {:.1f} C".format(last_temp), 0, 16)
    else:
        oled.text("Temp: --", 0, 16)

    if last_PID is not None:
        oled.text("Duty: {:.1f}".format(last_PID), 0, 24)
    else:
        oled.text("Duty: --", 0, 24)

    oled.text("OD  : {:.2f}".format(last_OD), 0, 32)
    oled.text("Flow: {:.1f} ml".format(last_volume), 0, 48)
    oled.text("Pump: {:.1f} s".format(last_pump), 0, 40)
    oled.show()

def update_temp(temp):
    global last_temp
    last_temp = temp
    _redraw()

def update_PID(PID):
    global last_PID
    last_PID = PID
    _redraw()

def show_quick_overview(OD_measurement, Volume_Transfered, pump_duration):
    global last_OD, last_volume, last_pump
    last_OD = OD_measurement
    last_volume = Volume_Transfered
    last_pump = pump_duration
    _redraw()
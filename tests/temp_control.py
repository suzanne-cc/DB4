from machine import Pin
import utime

from provided_code.read_temp import init_temp_sensor, read_temp
from pin_configuration import (
    TEMP_PUMP,
    THERMISTOR_PIN,
    FAN_PIN,
    PELTIER_PIN
)


# ============================================================
# SETTINGS
# ============================================================

TARGET_TEMP = 17.0

# Cooling turns on above:
# TARGET_TEMP + HYSTERESIS
#
# Cooling turns off below:
# TARGET_TEMP
HYSTERESIS = 0.2

# Peltier must remain on for at least this amount of time
MIN_PELTIER_ON_TIME_MS = 2000

# Time between temperature measurements
SAMPLE_TIME_MS = 1000


# ============================================================
# OUTPUT POLARITY
# ============================================================

# Keep these True if your driver turns on when the GPIO is HIGH.
# Change an individual value to False if that device works backwards.

FAN_ACTIVE_HIGH = True
PELTIER_ACTIVE_HIGH = True
PUMP_ACTIVE_HIGH = False


# ============================================================
# HARDWARE INITIALIZATION
# ============================================================

temperature_sensor = init_temp_sensor(THERMISTOR_PIN)

fan = Pin(FAN_PIN, Pin.OUT)
peltier = Pin(PELTIER_PIN, Pin.OUT)
pump = Pin(TEMP_PUMP, Pin.OUT)

def peltier_low():
    peltier.off()
    

def peltier_high():
    peltier.on()
    
    
def pump_off():
    pump.on()
    
def pump_on():
    pump.off()

# ============================================================
# INITIAL STATE
# ============================================================

# Fan is always on by default.
fan.off() #Fan is reversed

# Cooling starts off.
pump_off()

cooling_active = False
peltier_start_time = 0


# ============================================================
# START MESSAGE
# ============================================================

print("----------------------------------------")
print("Temperature control started")
print("Target temperature: {:.1f} C".format(TARGET_TEMP))
print(
    "Cooling turns ON above: {:.1f} C".format(
        TARGET_TEMP + HYSTERESIS
    )
)
print(
    "Cooling turns OFF at or below: {:.1f} C".format(
        TARGET_TEMP
    )
)
print("Minimum Peltier ON time: 2 seconds")
print("Fan: ALWAYS ON")
print("----------------------------------------")


# ============================================================
# MAIN CONTROL LOOP
# ============================================================

try:
    while True:

        temperature = read_temp(temperature_sensor)

        # ----------------------------------------------------
        # COOLING IS CURRENTLY OFF
        # ----------------------------------------------------

        if not cooling_active:

            # Start cooling when the temperature is too high.
            if temperature >= TARGET_TEMP + HYSTERESIS:

                pump_on()
                peltier_high()

                cooling_active = True
                peltier_start_time = utime.ticks_ms()

                print("Cooling switched ON")


        # ----------------------------------------------------
        # COOLING IS CURRENTLY ON
        # ----------------------------------------------------

        else:

            current_time = utime.ticks_ms()

            peltier_on_time = utime.ticks_diff(
                current_time,
                peltier_start_time
            )

            minimum_time_reached = (
                peltier_on_time >= MIN_PELTIER_ON_TIME_MS
            )

            # Only switch cooling off when:
            #
            # 1. The target temperature has been reached
            # 2. The Peltier has been on for at least 2 seconds

            if temperature <= TARGET_TEMP and minimum_time_reached:

                peltier_low()
                pump_off()

                cooling_active = False

                print("Cooling switched OFF")


       

        # ----------------------------------------------------
        # TERMINAL OUTPUT
        # ----------------------------------------------------

        if cooling_active:
            cooling_status = "ON"

            peltier_runtime = utime.ticks_diff(
                utime.ticks_ms(),
                peltier_start_time
            ) / 1000.0

        else:
            cooling_status = "OFF"
            peltier_runtime = 0.0


        print(
            "Temperature: {:.2f} C | "
            "Cooling: {} | "
            "Pump: {} | "
            "Peltier: {} | "
            "Peltier time: {:.1f} s | "
            .format(
                temperature,
                cooling_status,
                cooling_status,
                cooling_status,
                peltier_runtime
            )
        )


        utime.sleep_ms(SAMPLE_TIME_MS)


except KeyboardInterrupt:

    # Peltier and pump switch off when the program is stopped.
    peltier_low()
    pump_off()


    print("----------------------------------------")
    print("Temperature control stopped")
    print("Pump: OFF")
    print("Peltier: OFF")
    print("----------------------------------------")


except Exception as error:

    # Safe state if an unexpected error happens.
    peltier_low()
    pump.off()


    print("----------------------------------------")
    print("ERROR:", error)
    print("Pump: OFF")
    print("Peltier: OFF")
    print("----------------------------------------")

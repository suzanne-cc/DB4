# DB4 Autonomous Bioreactor

This Design Build 4 project is a MicroPython program for an ESP32 Feather
Huzzah32 bioreactor. The system is designed to house blue mussels
(*Mytilus edulis*) and automate feeding with microalgae (*Rhodomonas salina*)
inside a thermally controlled water bath.

The controller reads temperature from an NTC thermistor, regulates cooling with
a PID loop, estimates algae concentration with an optical sensor, doses algae
with an A4988 stepper driver, shows local status on an OLED display, and sends
telemetry to Adafruit IO over MQTT.

## Current Architecture

Startup flow:

```text
boot.py -> main.py -> temp_sensor.main()
```

The main controller is `temp_sensor.py`. It coordinates all sensors, actuators,
display updates, MQTT telemetry, and remote commands.

## Hardware Responsibilities

The controller currently supports:

- ESP32 Feather Huzzah32 running MicroPython.
- NTC thermistor on an ADC pin for water temperature.
- Peltier cooling module controlled by PWM.
- Relay output for cooling power.
- Heat-exchanger pump output.
- Circulation pump output.
- TCS34725 RGB/clear sensor for optical-density style algae measurement.
- A4988 stepper driver for algae dosing.
- I2C SSD1306 OLED display for local status.
- WiFi and MQTT telemetry to Adafruit IO.

## Main Files

### `main.py`

Small MicroPython entry point. After boot, it imports `temp_sensor` and starts
the main controller.

### `boot.py`

Runs before `main.py` on the ESP32. It is currently empty and safe to keep.

### `temp_sensor.py`

The main bioreactor brain.

It handles:

- Temperature control.
- PID cooling.
- Peltier PWM output.
- Relay and pump outputs.
- Optical-density reading.
- Automatic algae dosing.
- Manual dashboard feeding commands.
- OLED display updates.
- MQTT publishing and control-feed subscriptions.

Important constants to check before running on real hardware:

```python
TEMP_LOW_C = 17.0
TEMP_HIGH_C = 18.0
TARGET_TEMP_C = 17.5
TEMP_SENSOR_PIN = 32
I2C_SCL_PIN = 22
I2C_SDA_PIN = 23
PELTIER_PWM_PIN = 12
COOLING_RELAY_PIN = 13
HEAT_EXCHANGER_PUMP_PIN = 14
CIRCULATION_PUMP_PIN = 27
STEPPER_STEP_PIN = 26
STEPPER_DIR_PIN = 25
STEPPER_ENABLE_PIN = 33
STEPS_PER_ML = 200
OD_REFERENCE_CLEAR = 2000.0
```

### `read_temp.py`

Thermistor helper module.

It reads the ADC value, applies the calibration lookup table, converts the
reading to thermistor resistance, and returns temperature in Celsius.

This file can also be run by itself as a simple thermistor test.

### `MQTT.py`

WiFi and Adafruit IO helper module.

Set these values before uploading to the ESP32:

```python
WIFI_SSID = "wifi_SSID"
WIFI_PASSWORD = "password"
ADAFRUIT_USERNAME = "username"
ADAFRUIT_IO_KEY = "key"
```

The controller keeps running locally if WiFi or MQTT fails.

### `tcs34725.py`

Driver for the TCS34725 RGB/clear color sensor.

The main controller uses the clear channel as a simple optical-density signal.
The OD calculation depends on calibration with clean water or clean medium.

### `ssd1306.py`

Driver for the SSD1306 OLED display over I2C.

The main controller uses it to show temperature, cooling duty, OD, latest dose,
and short status messages.

### `i2c_test.py`

Standalone hardware test for the OLED and TCS34725 sensor.

Use this before running the full bioreactor controller if you want to confirm
that I2C wiring, the OLED, and the color sensor are working.

### `linearize.py`

ADC calibration script.

It uses the ESP32 DAC and ADC to build the lookup table used by `read_temp.py`.
You do not need to run this during normal operation, but it is useful if the ADC
calibration needs to be recreated.

### `pymakr.conf`

Pymakr upload configuration.

It tells Pymakr to ignore folders like `.git` and `venv` when uploading to the
board.

## Runtime Data Flow

Each control loop does roughly this:

1. Check MQTT command feeds if the dashboard is connected.
2. Read the thermistor temperature.
3. Calculate cooling output with the PID controller.
4. Apply PWM to the Peltier and switch relay/pump outputs.
5. Read optical-density data from the TCS34725 sensor.
6. Dose algae if OD is below target and feeding is allowed.
7. Update the OLED status screen.
8. Print one status line over serial.
9. Publish telemetry to Adafruit IO.
10. Wait until the next sample interval.

## Adafruit IO Feeds

Telemetry feeds:

- `temperature`
- `od`
- `pid-output`
- `cooling-duty`
- `feed-ml`
- `feed-steps`
- `color-clear`
- `status`

Remote control feeds:

- `target-temp`
- `manual-feed-ml`
- `cooling-enabled`
- `feeding-enabled`

## Calibration Checklist

Before trusting the controller with live animals, calibrate:

- `STEPS_PER_ML`: number of stepper pulses needed to dose 1 ml.
- `OD_REFERENCE_CLEAR`: clear-channel value in clean medium.
- `OD_TARGET`: desired algae concentration target.
- `ML_PER_OD_POINT`: dose amount for an OD deficit.
- PID gains: `KP`, `KI`, and `KD`.
- Relay polarity: `RELAY_ON` and `RELAY_OFF`.
- A4988 direction: `STEPPER_FEED_DIRECTION`.
- Actual wiring pin numbers.

## Testing On The Huzzah Board

Use `hardware_tests.py` for small smoke tests before running the full
bioreactor controller.

The safest first test is the OLED smiley test. Wire the OLED to the same I2C
pins used by the main program:

```text
OLED VCC -> 3V
OLED GND -> GND
OLED SCL -> GPIO 22
OLED SDA -> GPIO 23
```

Upload these files to the ESP32:

- `hardware_tests.py`
- `ssd1306.py`
- `tcs34725.py` if testing the color sensor
- `read_temp.py` if testing the thermistor

If `main.py` starts the full controller automatically, press `Ctrl-C` in the
serial console to stop it first. Then run tests from the MicroPython REPL.

### I2C Scan

```python
import hardware_tests
hardware_tests.i2c_scan()
```

Expected result:

- OLED usually appears at `0x3c`.
- TCS34725 usually appears at `0x29`.

### OLED Smiley Test

```python
import hardware_tests
hardware_tests.oled_smiley()
```

Expected result:

- The OLED clears.
- It shows `DB4 OLED OK`.
- A smiley face appears for 10 seconds.

You can also run `hardware_tests.py` directly from Pymakr. When run directly,
it performs an I2C scan and then draws the smiley.

### Thermistor Test

```python
import hardware_tests
hardware_tests.thermistor_once()
```

Expected result:

- The serial console prints raw ADC average, measured voltage, resistance, and
  temperature in Celsius.

If the value is wildly wrong, check:

- Thermistor wiring.
- Series resistor value in `read_temp.py`.
- ADC pin number.
- ADC lookup calibration.

### Color Sensor Test

```python
import hardware_tests
hardware_tests.color_sensor_once()
```

Expected result:

- The serial console prints raw `(R, G, B, clear)` readings.
- The clear value should change when you cover/uncover the sensor.

### LED Blink Test

```python
import hardware_tests
hardware_tests.blink_led()
```

Expected result:

- The selected pin blinks on and off.

Important: `ONBOARD_LED_PIN` is set to `13` in `hardware_tests.py`. If GPIO 13
is connected to a relay or another actuator in your wiring, do not run this
test until you change the pin number or disconnect the actuator.

## Files You Probably Do Not Need

The files `ai` and `ai.py` are empty. They are safe to delete if you are not
using them.

The `venv` folder is a local Python environment for PC-side tools and stubs. It
is not uploaded to the ESP32. In this project it also points to another Windows
user path in `venv/pyvenv.cfg`, so it is machine-specific and should not be
kept in Git long term.

Recommended `.gitignore` entries:

```gitignore
venv/
__pycache__/
*.pyc
```

## Suggested Keep/Delete Summary

Keep:

- `main.py`
- `boot.py`
- `temp_sensor.py`
- `read_temp.py`
- `MQTT.py`
- `tcs34725.py`
- `ssd1306.py`
- `i2c_test.py`
- `hardware_tests.py`
- `linearize.py`
- `pymakr.conf`
- `.vscode/settings.json` if using VS Code/Pymakr

Safe to delete:

- `ai`
- `ai.py`

Remove from Git or recreate locally:

- `venv`

## Notes

This project controls real electrical hardware and live biological conditions.
Test each output with safe dummy loads before connecting the Peltier, pumps, or
dosing system. Confirm that cooling turns off correctly before leaving the
system unattended.

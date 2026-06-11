"""Main controller for the DB4 autonomous mussel bioreactor.

This program runs on the ESP32 Feather Huzzah32 with MicroPython. It reads the
water temperature, controls cooling with a PID loop, measures algae density,
doses algae with an A4988 stepper driver, updates an OLED, and publishes MQTT
telemetry to Adafruit IO.
"""

from machine import I2C, Pin, PWM  # Load ESP32 hardware classes.
from math import log  # Load natural log for the OD calculation.
import utime  # Load MicroPython timing helpers.

import MQTT  # Load the local WiFi/MQTT helper.
import ssd1306  # Load the OLED display driver.
import tcs34725  # Load the RGB/clear optical sensor driver.
from read_temp import init_temp_sensor, read_temp_details  # Load thermistor helpers.


# --------------------------- Temperature targets ---------------------------

TEMP_LOW_C = 17.0  # Turn cooling fully off at or below this temperature.
TEMP_HIGH_C = 18.0  # Cooling should be active above this temperature.
TARGET_TEMP_C = 17.5  # Aim for the middle of the 17-18 C water-bath window.


# ------------------------------ Timing values ------------------------------

SAMPLE_INTERVAL_MS = 10000  # Run the main control loop every 10 seconds.
MQTT_RETRY_INTERVAL_MS = 60000  # Try dashboard reconnection every 60 seconds.
MIN_FEED_INTERVAL_MS = 30 * 60 * 1000  # Wait 30 minutes between automatic feeds.


# -------------------------------- Pin map ----------------------------------

TEMP_SENSOR_PIN = 32  # Read the NTC thermistor voltage on ADC pin 32.
I2C_SCL_PIN = 22  # Use GPIO 22 as I2C clock for OLED and optical sensor.
I2C_SDA_PIN = 23  # Use GPIO 23 as I2C data for OLED and optical sensor.
PELTIER_PWM_PIN = 12  # Drive the Peltier MOSFET/PWM input from GPIO 12.
COOLING_RELAY_PIN = 13  # Switch the Peltier power relay from GPIO 13.
HEAT_EXCHANGER_PUMP_PIN = 14  # Switch the heat-exchanger pump from GPIO 14.
CIRCULATION_PUMP_PIN = 27  # Keep water moving with a circulation pump on GPIO 27.
STEPPER_STEP_PIN = 26  # Send A4988 STEP pulses from GPIO 26.
STEPPER_DIR_PIN = 25  # Send A4988 DIR level from GPIO 25.
STEPPER_ENABLE_PIN = 33  # Send A4988 ENABLE level from GPIO 33.


# --------------------------- Hardware settings -----------------------------

PWM_FREQ_HZ = 1000  # Use 1 kHz PWM for the cooling output.
PWM_DUTY_MAX = 1023  # ESP32 MicroPython PWM duty range is usually 0-1023.
RELAY_ON = 1  # Use active-high relay modules by default.
RELAY_OFF = 0  # Use low output to turn default relay modules off.
STEPPER_ENABLE_ON = 0  # A4988 ENABLE is active-low.
STEPPER_ENABLE_OFF = 1  # A4988 is disabled when ENABLE is high.
STEPPER_FEED_DIRECTION = 1  # Change this to 0 if the dosing pump runs backward.
STEPPER_STEP_DELAY_US = 900  # Delay between step edges; larger is slower/safer.
STEPS_PER_ML = 200  # Calibrate this to your pump: motor steps needed for 1 ml.


# ----------------------------- PID settings --------------------------------

KP = 250.0  # Proportional gain; raises cooling quickly when water is warm.
KI = 2.0  # Integral gain; corrects slow long-term temperature errors.
KD = 40.0  # Derivative gain; reduces overshoot when temperature changes fast.
PID_INTEGRAL_LIMIT = 200.0  # Limit stored error so the controller cannot wind up.


# -------------------------- Optical density setup --------------------------

OD_REFERENCE_CLEAR = 2000.0  # Clear-water sensor value; calibrate this in clean medium.
OD_TARGET = 0.35  # Desired algae optical-density estimate.
OD_DEADBAND = 0.03  # Do not feed when OD is close enough to the target.
ML_PER_OD_POINT = 5.0  # Dosed ml for one full OD unit below target.
MAX_AUTO_DOSE_ML = 1.0  # Maximum automatic dose in one control loop.
MAX_MANUAL_DOSE_ML = 10.0  # Maximum remote/manual dose in one command.
TCS_INTEGRATION_MS = 50.0  # RGB sensor integration time.
TCS_GAIN = 16  # RGB sensor gain; valid values are 1, 4, 16, and 60.
LOG_10 = log(10)  # Store log(10) so we can calculate log10 on MicroPython.


# ------------------------------- OLED setup --------------------------------

OLED_WIDTH = 128  # OLED display width in pixels.
OLED_HEIGHT = 64  # OLED display height in pixels.


def clamp(value, minimum, maximum):
    """Keep a value inside a minimum and maximum."""
    if value < minimum:  # Check whether the value is too small.
        return minimum  # Return the lowest allowed value.

    if value > maximum:  # Check whether the value is too large.
        return maximum  # Return the highest allowed value.

    return value  # Return the original value when it is already safe.


def text_value(value):
    """Convert bytes or numbers to readable text."""
    if isinstance(value, bytes):  # Check whether MQTT gave us bytes.
        return value.decode("utf-8").strip()  # Decode and remove whitespace.

    return str(value).strip()  # Convert other values to text and trim spaces.


def bool_value(value):
    """Convert common dashboard words to True or False."""
    text = text_value(value).lower()  # Normalize the incoming text.

    if text in ("1", "true", "on", "yes", "enable", "enabled"):  # Match true words.
        return True  # Return enabled.

    if text in ("0", "false", "off", "no", "disable", "disabled"):  # Match false words.
        return False  # Return disabled.

    return None  # Return unknown when the text does not match.


def number_value(value, fallback=None):
    """Convert dashboard text to a float, or return fallback if it fails."""
    try:  # Try conversion because dashboard messages may be invalid.
        return float(text_value(value))  # Parse the value as a number.

    except Exception:  # Catch bad text like "hello".
        return fallback  # Return the safe fallback value.


def format_value(value, decimals=1):
    """Format numbers for the OLED without crashing on missing sensors."""
    if value is None:  # Check for unavailable hardware or missing data.
        return "--"  # Show dashes when there is no value.

    return str(round(value, decimals))  # Round and convert the number to text.


def make_output(pin_no, initial_value=0):
    """Create one digital output pin with an initial state."""
    pin = Pin(pin_no, Pin.OUT)  # Create the GPIO output.
    pin.value(initial_value)  # Set the safe starting value.
    return pin  # Return the configured pin.


class PIDController:
    """Simple PID controller that outputs a PWM duty for cooling."""

    def __init__(self, kp, ki, kd, setpoint, output_min, output_max, integral_limit):
        self.kp = kp  # Store proportional gain.
        self.ki = ki  # Store integral gain.
        self.kd = kd  # Store derivative gain.
        self.setpoint = setpoint  # Store the desired temperature.
        self.output_min = output_min  # Store the minimum output duty.
        self.output_max = output_max  # Store the maximum output duty.
        self.integral_limit = integral_limit  # Store the anti-windup limit.
        self.integral = 0.0  # Start with no accumulated error.
        self.previous_error = None  # Wait for a first reading before derivative math.
        self.previous_ms = utime.ticks_ms()  # Store the current time.
        self.last_p = 0.0  # Store the latest proportional term for telemetry.
        self.last_i = 0.0  # Store the latest integral term for telemetry.
        self.last_d = 0.0  # Store the latest derivative term for telemetry.

    def reset(self):
        self.integral = 0.0  # Clear stored error.
        self.previous_error = None  # Clear previous error.
        self.previous_ms = utime.ticks_ms()  # Restart timing from now.
        self.last_p = 0.0  # Clear P telemetry.
        self.last_i = 0.0  # Clear I telemetry.
        self.last_d = 0.0  # Clear D telemetry.

    def update(self, measured_temp):
        now_ms = utime.ticks_ms()  # Read the current time.
        dt = utime.ticks_diff(now_ms, self.previous_ms) / 1000.0  # Convert elapsed time to seconds.

        if dt <= 0:  # Protect against zero or negative time differences.
            dt = 0.001  # Use a tiny time step.

        error = measured_temp - self.setpoint  # Positive error means water is too warm.
        self.integral += error * dt  # Add this error to the integral store.
        self.integral = clamp(self.integral, -self.integral_limit, self.integral_limit)  # Limit windup.

        if self.previous_error is None:  # Check whether this is the first PID update.
            derivative = 0.0  # Skip derivative on the first sample.
        else:  # Use the previous sample after the first update.
            derivative = (error - self.previous_error) / dt  # Calculate error speed.

        self.last_p = self.kp * error  # Calculate proportional output.
        self.last_i = self.ki * self.integral  # Calculate integral output.
        self.last_d = self.kd * derivative  # Calculate derivative output.
        raw_output = self.last_p + self.last_i + self.last_d  # Add PID terms.
        output = clamp(raw_output, self.output_min, self.output_max)  # Keep output in PWM range.
        self.previous_error = error  # Save error for the next derivative.
        self.previous_ms = now_ms  # Save time for the next update.
        return output  # Return the cooling duty request.


class A4988Doser:
    """Drive a stepper-based dosing pump through an A4988 driver."""

    def __init__(self, step_pin_no, dir_pin_no, enable_pin_no, steps_per_ml):
        self.step_pin = make_output(step_pin_no, 0)  # Create STEP output and hold it low.
        self.dir_pin = make_output(dir_pin_no, STEPPER_FEED_DIRECTION)  # Create DIR output.
        self.enable_pin = make_output(enable_pin_no, STEPPER_ENABLE_OFF)  # Disable the driver at start.
        self.steps_per_ml = steps_per_ml  # Store pump calibration.

    def enable(self):
        self.enable_pin.value(STEPPER_ENABLE_ON)  # Pull ENABLE low so the A4988 drives the motor.
        utime.sleep_ms(2)  # Give the driver a moment to wake up.

    def disable(self):
        self.enable_pin.value(STEPPER_ENABLE_OFF)  # Pull ENABLE high so the motor is idle.

    def dose_ml(self, amount_ml):
        amount_ml = max(0.0, amount_ml)  # Remove negative dosing requests.
        steps = int(amount_ml * self.steps_per_ml + 0.5)  # Convert ml to whole motor steps.

        if steps <= 0:  # Skip if the dose is too small.
            return 0  # Report no steps.

        self.dir_pin.value(STEPPER_FEED_DIRECTION)  # Set the pump direction.
        self.enable()  # Turn on the A4988 driver.

        for _ in range(steps):  # Send one pulse for each motor step.
            self.step_pin.value(1)  # Raise STEP.
            utime.sleep_us(STEPPER_STEP_DELAY_US)  # Hold STEP high briefly.
            self.step_pin.value(0)  # Lower STEP.
            utime.sleep_us(STEPPER_STEP_DELAY_US)  # Wait before the next step.

        self.disable()  # Turn off the motor driver after dosing.
        return steps  # Report how many steps were sent.


class BioreactorState:
    """Mutable settings controlled locally and through MQTT feeds."""

    def __init__(self):
        self.target_temp_c = TARGET_TEMP_C  # Store the active target temperature.
        self.cooling_enabled = True  # Allow cooling by default.
        self.feeding_enabled = True  # Allow automatic feeding by default.
        self.manual_feed_ml = 0.0  # Store pending manual feed amount.
        self.last_feed_ms = utime.ticks_ms() - MIN_FEED_INTERVAL_MS  # Allow feeding immediately if OD is low.
        self.last_mqtt_attempt_ms = 0  # Store the last dashboard connection attempt.
        self.status = "starting"  # Store a short status message.


def setup_i2c():
    """Create the shared I2C bus for OLED and optical sensor."""
    try:  # Hardware setup can fail if pins or devices are wrong.
        return I2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100000)  # Create the I2C bus.

    except Exception as error:  # Catch I2C setup errors.
        print("I2C setup failed:", type(error).__name__, error)  # Show the problem.
        return None  # Continue without I2C hardware.


def setup_oled(i2c):
    """Create the OLED object when the display is connected."""
    if i2c is None:  # Check whether I2C exists.
        return None  # Skip OLED setup when I2C failed.

    try:  # OLED setup can fail if the display is not attached.
        oled = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)  # Create the display.
        oled.fill(0)  # Clear the screen buffer.
        oled.text("DB4 starting", 0, 0)  # Put a boot message on the screen.
        oled.show()  # Send the buffer to the OLED.
        return oled  # Return the display object.

    except Exception as error:  # Catch missing display errors.
        print("OLED setup failed:", type(error).__name__, error)  # Show the problem.
        return None  # Continue without local display.


def setup_od_sensor(i2c):
    """Create the TCS34725 optical-density sensor when connected."""
    if i2c is None:  # Check whether I2C exists.
        return None  # Skip the sensor when I2C failed.

    try:  # Sensor setup can fail if the device is missing.
        sensor = tcs34725.TCS34725(i2c)  # Create the color sensor object.
        sensor.integration_time(TCS_INTEGRATION_MS)  # Set integration time.
        sensor.gain(TCS_GAIN)  # Set sensor gain.
        return sensor  # Return the sensor object.

    except Exception as error:  # Catch missing/wrong sensor errors.
        print("OD sensor setup failed:", type(error).__name__, error)  # Show the problem.
        return None  # Continue without automatic OD feeding.


def read_od(sensor):
    """Read optical-density information from the color sensor."""
    if sensor is None:  # Check whether an OD sensor is available.
        return {"od": None, "r": None, "g": None, "b": None, "clear": None}  # Return empty data.

    raw = sensor.read(True)  # Read raw red, green, blue, and clear channels.
    r, g, b, clear = raw  # Split the raw tuple into named values.

    if clear <= 0 or OD_REFERENCE_CLEAR <= 0:  # Avoid log problems in darkness or bad calibration.
        od = None  # Mark OD as unavailable.
    else:  # Calculate OD when clear light is valid.
        ratio = clear / OD_REFERENCE_CLEAR  # Compare current light to clear-water light.
        od = -log(ratio) / LOG_10  # Convert transmitted light to optical density.
        od = max(0.0, od)  # Clamp negative values to zero.

    return {"od": od, "r": r, "g": g, "b": b, "clear": clear}  # Return all OD values.


def setup_actuators():
    """Create the cooling, pump, relay, and dosing outputs."""
    peltier_pwm = PWM(Pin(PELTIER_PWM_PIN, Pin.OUT), freq=PWM_FREQ_HZ)  # Create cooling PWM.
    peltier_pwm.duty(0)  # Start with the Peltier off.
    cooling_relay = make_output(COOLING_RELAY_PIN, RELAY_OFF)  # Create the Peltier relay output.
    heat_exchanger_pump = make_output(HEAT_EXCHANGER_PUMP_PIN, RELAY_OFF)  # Create exchanger pump output.
    circulation_pump = make_output(CIRCULATION_PUMP_PIN, RELAY_ON)  # Start circulation immediately.
    doser = A4988Doser(STEPPER_STEP_PIN, STEPPER_DIR_PIN, STEPPER_ENABLE_PIN, STEPS_PER_ML)  # Create doser.
    return peltier_pwm, cooling_relay, heat_exchanger_pump, circulation_pump, doser  # Return all outputs.


def set_cooling(duty, peltier_pwm, cooling_relay, heat_exchanger_pump, circulation_pump, enabled):
    """Apply the cooling duty to Peltier, relay, and pumps."""
    if not enabled:  # Check whether remote control disabled cooling.
        duty = 0  # Force cooling off.

    duty = int(clamp(duty, 0, PWM_DUTY_MAX))  # Clamp to the ESP32 PWM range.
    peltier_pwm.duty(duty)  # Send PWM to the Peltier driver.
    active = duty > 0  # Decide whether cooling hardware should be energized.
    cooling_relay.value(RELAY_ON if active else RELAY_OFF)  # Switch Peltier power.
    heat_exchanger_pump.value(RELAY_ON if active else RELAY_OFF)  # Move water through exchanger only while cooling.
    circulation_pump.value(RELAY_ON)  # Keep bath water circulating all the time.
    return duty  # Return the actual applied duty.


def stop_outputs(peltier_pwm, cooling_relay, heat_exchanger_pump, circulation_pump, doser):
    """Put moving or powered hardware into a safe idle state."""
    peltier_pwm.duty(0)  # Stop Peltier PWM.
    cooling_relay.value(RELAY_OFF)  # Turn off Peltier relay.
    heat_exchanger_pump.value(RELAY_OFF)  # Turn off exchanger pump.
    circulation_pump.value(RELAY_OFF)  # Turn off circulation pump on shutdown.
    doser.disable()  # Disable the stepper driver.


def calculate_auto_dose_ml(od, state):
    """Decide how much algae to dose from the current OD value."""
    if not state.feeding_enabled:  # Respect remote/local feeding disable.
        return 0.0  # Do not feed.

    if od is None:  # Require a valid OD reading for automatic feeding.
        return 0.0  # Do not feed without sensor data.

    if od >= OD_TARGET - OD_DEADBAND:  # Check whether food concentration is high enough.
        return 0.0  # Do not feed inside the target band.

    since_feed_ms = utime.ticks_diff(utime.ticks_ms(), state.last_feed_ms)  # Measure time since last feed.

    if since_feed_ms < MIN_FEED_INTERVAL_MS:  # Prevent frequent small doses.
        return 0.0  # Wait until the minimum interval has passed.

    od_gap = OD_TARGET - od  # Calculate how far below target we are.
    dose_ml = od_gap * ML_PER_OD_POINT  # Convert OD shortage to a dose.
    dose_ml = clamp(dose_ml, 0.0, MAX_AUTO_DOSE_ML)  # Limit one automatic dose.
    return dose_ml  # Return the requested dose.


def handle_feeding(od, state, doser):
    """Run manual or automatic feeding and return dose details."""
    dose_ml = 0.0  # Start with no dose.
    dose_reason = "none"  # Start with no dose reason.

    if state.manual_feed_ml > 0:  # Check whether the dashboard requested a manual feed.
        dose_ml = clamp(state.manual_feed_ml, 0.0, MAX_MANUAL_DOSE_ML)  # Limit manual feed size.
        state.manual_feed_ml = 0.0  # Clear the command so it runs once.
        dose_reason = "manual"  # Mark the dose source.

    else:  # Use automatic feeding when no manual command is waiting.
        dose_ml = calculate_auto_dose_ml(od, state)  # Calculate automatic dose.
        if dose_ml > 0:  # Check whether automatic feeding is needed.
            dose_reason = "auto"  # Mark the dose source.

    if dose_ml <= 0:  # Skip motor movement when no food is needed.
        return 0.0, 0, dose_reason  # Return no dose.

    steps = doser.dose_ml(dose_ml)  # Run the dosing pump.
    state.last_feed_ms = utime.ticks_ms()  # Store the feed time.
    return dose_ml, steps, dose_reason  # Return dose telemetry.


def build_feeds():
    """Create all Adafruit IO feed topics used by this controller."""
    return {  # Return a dictionary of feed-name to MQTT topic.
        "temperature": MQTT.make_feed("temperature"),  # Temperature telemetry.
        "od": MQTT.make_feed("od"),  # Optical-density telemetry.
        "pid_output": MQTT.make_feed("pid-output"),  # PID duty request.
        "cooling_duty": MQTT.make_feed("cooling-duty"),  # Applied cooling duty.
        "feed_ml": MQTT.make_feed("feed-ml"),  # Actual dosed milliliters.
        "feed_steps": MQTT.make_feed("feed-steps"),  # Actual stepper pulses.
        "color_clear": MQTT.make_feed("color-clear"),  # Raw clear-channel sensor data.
        "status": MQTT.make_feed("status"),  # Short text status.
        "target_temp": MQTT.make_feed("target-temp"),  # Remote command for target temperature.
        "manual_feed": MQTT.make_feed("manual-feed-ml"),  # Remote command for one manual dose.
        "cooling_enabled": MQTT.make_feed("cooling-enabled"),  # Remote command to enable/disable cooling.
        "feeding_enabled": MQTT.make_feed("feeding-enabled"),  # Remote command to enable/disable feeding.
    }


def handle_control_message(topic, message, state, pid):
    """React to incoming Adafruit IO control-feed updates."""
    topic_text = text_value(topic)  # Convert the MQTT topic to text.
    message_text = text_value(message)  # Convert the MQTT payload to text.
    print("MQTT command:", topic_text, message_text)  # Show the command on serial.

    if topic_text.endswith("/target-temp"):  # Check for target-temperature command.
        target = number_value(message_text, state.target_temp_c)  # Parse the requested temperature.
        target = clamp(target, 5.0, 30.0)  # Limit to a safe biological range.
        state.target_temp_c = target  # Store the new target.
        pid.setpoint = target  # Update the PID setpoint.
        pid.reset()  # Reset PID memory after a target jump.
        state.status = "target set"  # Update status text.

    elif topic_text.endswith("/manual-feed-ml"):  # Check for manual feed command.
        amount = number_value(message_text, 0.0)  # Parse the requested ml.
        state.manual_feed_ml = clamp(amount, 0.0, MAX_MANUAL_DOSE_ML)  # Store a safe one-shot dose.
        state.status = "manual feed queued"  # Update status text.

    elif topic_text.endswith("/cooling-enabled"):  # Check for cooling enable command.
        enabled = bool_value(message_text)  # Parse true/false text.
        if enabled is not None:  # Apply only recognized values.
            state.cooling_enabled = enabled  # Store cooling state.
            state.status = "cooling toggled"  # Update status text.

    elif topic_text.endswith("/feeding-enabled"):  # Check for feeding enable command.
        enabled = bool_value(message_text)  # Parse true/false text.
        if enabled is not None:  # Apply only recognized values.
            state.feeding_enabled = enabled  # Store feeding state.
            state.status = "feeding toggled"  # Update status text.


def configure_mqtt_controls(client, feeds, state, pid):
    """Subscribe to remote control feeds when MQTT is online."""
    if client is None:  # Check whether MQTT is connected.
        return  # Skip setup when offline.

    def callback(topic, message):  # Define the callback used by MQTTClient.
        handle_control_message(topic, message, state, pid)  # Handle the command.

    client.set_callback(callback)  # Register the callback with the MQTT client.
    MQTT.subscribe(client, feeds["target_temp"])  # Listen for target temperature updates.
    MQTT.subscribe(client, feeds["manual_feed"])  # Listen for manual feed commands.
    MQTT.subscribe(client, feeds["cooling_enabled"])  # Listen for cooling enable commands.
    MQTT.subscribe(client, feeds["feeding_enabled"])  # Listen for feeding enable commands.


def connect_dashboard(state, pid, feeds):
    """Connect WiFi and MQTT dashboard features."""
    wifi = MQTT.connect_wifi()  # Connect to the local WiFi network.

    if wifi is None:  # Check whether WiFi failed.
        state.status = "wifi offline"  # Store status for display/publishing.
        return None, None  # Return offline dashboard objects.

    client = MQTT.connect_mqtt()  # Connect to Adafruit IO.

    if client is None:  # Check whether MQTT failed.
        state.status = "mqtt offline"  # Store status for display.
        return wifi, None  # Keep WiFi but skip MQTT.

    configure_mqtt_controls(client, feeds, state, pid)  # Subscribe to dashboard command feeds.
    state.status = "dashboard online"  # Store status.
    return wifi, client  # Return connected dashboard objects.


def reconnect_dashboard_if_needed(client, state, pid, feeds):
    """Try to reconnect MQTT occasionally when the dashboard is offline."""
    if client is not None:  # Keep the existing client when it is connected.
        return client  # Return the current client.

    now_ms = utime.ticks_ms()  # Read the current time.

    if utime.ticks_diff(now_ms, state.last_mqtt_attempt_ms) < MQTT_RETRY_INTERVAL_MS:  # Rate-limit retries.
        return None  # Wait longer before retrying.

    state.last_mqtt_attempt_ms = now_ms  # Store the retry time.
    _, new_client = connect_dashboard(state, pid, feeds)  # Try a fresh dashboard connection.
    return new_client  # Return the new client or None.


def check_dashboard_messages(client):
    """Process incoming MQTT command messages without stopping control."""
    if client is None:  # Skip when offline.
        return None  # Return no error.

    try:  # MQTT check can fail if WiFi drops.
        client.check_msg()  # Let the MQTT client call our command callback.
        return client  # Return the still-working client.

    except Exception as error:  # Catch WiFi/MQTT drops.
        print("MQTT check failed:", type(error).__name__, error)  # Show the failure.
        return None  # Force a later reconnect.


def publish_telemetry(client, feeds, temp, od_data, pid_output, cooling_duty, dose_ml, dose_steps, state):
    """Publish the latest bioreactor state to Adafruit IO."""
    if client is None:  # Skip publishing when offline.
        return None  # Return no client.

    ok = True  # Track whether all publishes worked.
    ok = MQTT.publish(client, feeds["temperature"], temp) and ok  # Publish water temperature.
    ok = MQTT.publish(client, feeds["od"], od_data["od"]) and ok  # Publish OD estimate.
    ok = MQTT.publish(client, feeds["pid_output"], pid_output) and ok  # Publish PID output.
    ok = MQTT.publish(client, feeds["cooling_duty"], cooling_duty, decimals=0) and ok  # Publish PWM duty.
    ok = MQTT.publish(client, feeds["feed_ml"], dose_ml) and ok  # Publish dose amount.
    ok = MQTT.publish(client, feeds["feed_steps"], dose_steps, decimals=0) and ok  # Publish step count.
    ok = MQTT.publish(client, feeds["color_clear"], od_data["clear"], decimals=0) and ok  # Publish clear channel.
    ok = MQTT.publish(client, feeds["status"], state.status) and ok  # Publish status text.

    if not ok:  # Check whether any publish failed.
        return None  # Force a later reconnect.

    return client  # Keep the connected client.


def update_oled(oled, temp, od_data, cooling_duty, dose_ml, state):
    """Draw a compact status screen on the OLED."""
    if oled is None:  # Skip when no display is connected.
        return  # Nothing to draw.

    oled.fill(0)  # Clear the display buffer.
    oled.text("DB4 bioreactor", 0, 0)  # Show the project name.
    oled.text("T " + format_value(temp) + "/" + format_value(state.target_temp_c) + "C", 0, 10)  # Show temp.
    oled.text("Cool " + str(cooling_duty), 0, 20)  # Show cooling PWM duty.
    oled.text("OD " + format_value(od_data["od"], 2), 0, 30)  # Show algae OD.
    oled.text("Feed " + format_value(dose_ml, 2) + " ml", 0, 40)  # Show latest dose.
    oled.text(state.status[:16], 0, 54)  # Show short status text.
    oled.show()  # Send the buffer to the screen.


def print_status(temp, od_data, pid_output, cooling_duty, dose_ml, dose_steps, state):
    """Print one readable status line to the serial monitor."""
    print(  # Print compact telemetry for debugging.
        "T={}C target={}C OD={} clear={} PID={} duty={} dose={}ml steps={} status={}".format(
            format_value(temp),  # Insert measured temperature.
            format_value(state.target_temp_c),  # Insert target temperature.
            format_value(od_data["od"], 2),  # Insert optical density.
            od_data["clear"],  # Insert raw clear-channel value.
            format_value(pid_output, 0),  # Insert PID output.
            cooling_duty,  # Insert applied cooling duty.
            format_value(dose_ml, 2),  # Insert dose ml.
            dose_steps,  # Insert motor step count.
            state.status,  # Insert current status text.
        )
    )


def main():
    """Start and run the complete autonomous bioreactor controller."""
    print("DB4 bioreactor controller starting.")  # Announce startup on serial.
    state = BioreactorState()  # Create shared controller state.
    pid = PIDController(KP, KI, KD, state.target_temp_c, 0, PWM_DUTY_MAX, PID_INTEGRAL_LIMIT)  # Create PID.
    temp_sensor = init_temp_sensor(TEMP_SENSOR_PIN)  # Create the thermistor ADC input.
    i2c = setup_i2c()  # Create the shared I2C bus.
    oled = setup_oled(i2c)  # Create the OLED display if present.
    od_sensor = setup_od_sensor(i2c)  # Create the OD sensor if present.
    outputs = setup_actuators()  # Create cooling, pump, and dosing outputs.
    peltier_pwm, cooling_relay, heat_exchanger_pump, circulation_pump, doser = outputs  # Name the outputs.
    feeds = build_feeds()  # Build MQTT feed topics.
    _, client = connect_dashboard(state, pid, feeds)  # Connect WiFi/MQTT if possible.

    while True:  # Run forever until the board resets or the user stops it.
        try:  # Keep one bad sensor/network event from killing the controller.
            client = reconnect_dashboard_if_needed(client, state, pid, feeds)  # Reconnect dashboard if offline.
            client = check_dashboard_messages(client)  # Process remote control messages.

            temp_details = read_temp_details(temp_sensor)  # Read thermistor details.
            temp = temp_details["temperature"]  # Extract Celsius temperature.
            pid.setpoint = state.target_temp_c  # Keep PID target synced with state.

            if temp <= TEMP_LOW_C:  # Check if the water is already cool enough.
                pid.reset()  # Clear PID memory while cooling is off.
                pid_output = 0  # Request no cooling.
                state.status = "cool enough"  # Update status.
            else:  # Use PID when temperature is above the lower limit.
                pid_output = pid.update(temp)  # Calculate cooling request.
                if temp >= TEMP_HIGH_C:  # Check whether water is above the allowed band.
                    state.status = "above 18C"  # Make the high-temperature case visible.
                else:  # Water is warm but still inside the 17-18 C band.
                    state.status = "cooling" if pid_output > 0 else "holding"  # Update status.

            cooling_duty = set_cooling(  # Apply cooling request to real hardware.
                pid_output,  # Send PID output.
                peltier_pwm,  # Send the PWM object.
                cooling_relay,  # Send relay output.
                heat_exchanger_pump,  # Send exchanger pump output.
                circulation_pump,  # Send circulation pump output.
                state.cooling_enabled,  # Respect remote cooling toggle.
            )

            if not state.cooling_enabled:  # Check whether dashboard disabled cooling.
                state.status = "cooling off"  # Make disabled cooling visible.

            od_data = read_od(od_sensor)  # Read algae optical-density data.
            dose_ml, dose_steps, dose_reason = handle_feeding(od_data["od"], state, doser)  # Feed if needed.

            if dose_ml > 0:  # Check whether feeding happened.
                state.status = "fed " + dose_reason  # Update status after a dose.

            update_oled(oled, temp, od_data, cooling_duty, dose_ml, state)  # Refresh local display.
            print_status(temp, od_data, pid_output, cooling_duty, dose_ml, dose_steps, state)  # Print serial status.
            client = publish_telemetry(client, feeds, temp, od_data, pid_output, cooling_duty, dose_ml, dose_steps, state)  # Publish dashboard data.
            utime.sleep_ms(SAMPLE_INTERVAL_MS)  # Wait until the next control cycle.

        except KeyboardInterrupt:  # Allow Ctrl-C during serial testing.
            print("Stopping DB4 controller.")  # Explain shutdown.
            stop_outputs(peltier_pwm, cooling_relay, heat_exchanger_pump, circulation_pump, doser)  # Stop hardware.
            break  # Leave the control loop.

        except Exception as error:  # Catch unexpected sensor or actuator errors.
            print("Controller error:", type(error).__name__, error)  # Show the error.
            state.status = "error"  # Store error status.
            set_cooling(0, peltier_pwm, cooling_relay, heat_exchanger_pump, circulation_pump, False)  # Stop cooling safely.
            update_oled(oled, None, {"od": None}, 0, 0.0, state)  # Show error on OLED if possible.
            utime.sleep_ms(SAMPLE_INTERVAL_MS)  # Pause before trying again.


if __name__ == "__main__":  # Run main only when this file is launched directly.
    main()  # Start the bioreactor controller.

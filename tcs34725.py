"""TCS34725 RGB/color sensor driver for MicroPython."""

import time  # Load sleep helpers for sensor integration waits.
import ustruct  # Load binary pack/unpack helpers for I2C registers.

try:  # MicroPython normally provides const as a built-in.
    const  # Check whether const already exists.
except NameError:  # CPython-style tools do not have const.
    const = lambda value: value  # Keep the same syntax during local checks.


_COMMAND_BIT = const(0x80)  # Mark I2C register access as a command.

_REGISTER_ENABLE = const(0x00)  # Enable register address.
_REGISTER_ATIME = const(0x01)  # Integration-time register address.
_REGISTER_AILT = const(0x04)  # Low interrupt threshold register.
_REGISTER_AIHT = const(0x06)  # High interrupt threshold register.
_REGISTER_APERS = const(0x0C)  # Interrupt persistence register.
_REGISTER_CONTROL = const(0x0F)  # Gain control register.
_REGISTER_SENSORID = const(0x12)  # Sensor ID register.
_REGISTER_STATUS = const(0x13)  # Sensor status register.
_REGISTER_CDATA = const(0x14)  # Clear channel register.
_REGISTER_RDATA = const(0x16)  # Red channel register.
_REGISTER_GDATA = const(0x18)  # Green channel register.
_REGISTER_BDATA = const(0x1A)  # Blue channel register.

_ENABLE_AIEN = const(0x10)  # Interrupt enable bit.
_ENABLE_AEN = const(0x02)  # ADC enable bit.
_ENABLE_PON = const(0x01)  # Power enable bit.

_GAINS = (1, 4, 16, 60)  # Valid sensor gain values.
_CYCLES = (0, 1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60)  # Interrupt cycle choices.


class TCS34725:
    """Read raw RGB/clear values and derived lux/color temperature."""

    def __init__(self, i2c, address=0x29):
        self.i2c = i2c  # Store the I2C bus object.
        self.address = address  # Store the sensor I2C address.
        self._active = False  # Track whether the sensor is powered for reads.
        self.integration_time(2.4)  # Start with the shortest integration time.

        sensor_id = self.sensor_id()  # Read the sensor ID register.
        if sensor_id not in (0x44, 0x10):  # Check the known TCS34725 IDs.
            raise RuntimeError("wrong sensor id 0x{:x}".format(sensor_id))  # Stop on wrong hardware.

    def _register8(self, register, value=None):
        register |= _COMMAND_BIT  # Add the command bit to the register address.

        if value is None:  # Read mode is used when no value is supplied.
            return self.i2c.readfrom_mem(self.address, register, 1)[0]  # Return one byte.

        data = ustruct.pack("<B", value)  # Pack one byte for writing.
        self.i2c.writeto_mem(self.address, register, data)  # Write the byte to the sensor.

    def _register16(self, register, value=None):
        register |= _COMMAND_BIT  # Add the command bit to the register address.

        if value is None:  # Read mode is used when no value is supplied.
            data = self.i2c.readfrom_mem(self.address, register, 2)  # Read two bytes.
            return ustruct.unpack("<H", data)[0]  # Convert little-endian bytes to an integer.

        data = ustruct.pack("<H", value)  # Pack a 16-bit value for writing.
        self.i2c.writeto_mem(self.address, register, data)  # Write the value to the sensor.

    def active(self, value=None):
        if value is None:  # Return current state when no value is supplied.
            return self._active

        value = bool(value)  # Convert the requested state to True/False.

        if self._active == value:  # Avoid repeated register writes.
            return

        self._active = value  # Store the new state.
        enable = self._register8(_REGISTER_ENABLE)  # Read the current enable flags.

        if value:  # Turn the sensor on.
            self._register8(_REGISTER_ENABLE, enable | _ENABLE_PON)  # Power the chip.
            time.sleep_ms(3)  # Wait for the oscillator to start.
            self._register8(_REGISTER_ENABLE, enable | _ENABLE_PON | _ENABLE_AEN)  # Enable ADC reads.
        else:  # Turn the sensor off.
            self._register8(_REGISTER_ENABLE, enable & ~(_ENABLE_PON | _ENABLE_AEN))  # Disable power/ADC.

    def sensor_id(self):
        return self._register8(_REGISTER_SENSORID)  # Return the chip identification byte.

    def integration_time(self, value=None):
        if value is None:  # Return the current setting when no value is supplied.
            return self._integration_time

        value = min(614.4, max(2.4, value))  # Clamp integration time to sensor limits.
        cycles = int(value / 2.4)  # Convert milliseconds to sensor cycles.
        self._integration_time = cycles * 2.4  # Store the real rounded integration time.
        return self._register8(_REGISTER_ATIME, 256 - cycles)  # Write integration time register.

    def gain(self, value=None):
        if value is None:  # Return the current gain when no value is supplied.
            return _GAINS[self._register8(_REGISTER_CONTROL)]  # Decode the gain register.

        if value not in _GAINS:  # Validate requested gain.
            raise ValueError("gain must be 1, 4, 16 or 60")  # Explain accepted values.

        return self._register8(_REGISTER_CONTROL, _GAINS.index(value))  # Write gain index.

    def _valid(self):
        return bool(self._register8(_REGISTER_STATUS) & 0x01)  # True means fresh color data exists.

    def read(self, raw=False):
        was_active = self.active()  # Remember whether the sensor was already on.
        self.active(True)  # Turn the sensor on for the reading.

        while not self._valid():  # Wait until the integration is complete.
            time.sleep_ms(int(self._integration_time + 0.9))  # Sleep roughly one integration period.

        data = tuple(  # Read red, green, blue, and clear channels.
            self._register16(register)  # Read one 16-bit channel.
            for register in (_REGISTER_RDATA, _REGISTER_GDATA, _REGISTER_BDATA, _REGISTER_CDATA)
        )

        self.active(was_active)  # Restore the previous power state.

        if raw:  # Return raw sensor channels when requested.
            return data

        return self._temperature_and_lux(data)  # Return derived color temperature and lux.

    def _temperature_and_lux(self, data):
        r, g, b, _ = data  # Split the raw channels.
        x = -0.14282 * r + 1.54924 * g - 0.95641 * b  # Estimate CIE X.
        y = -0.32466 * r + 1.57837 * g - 0.73191 * b  # Estimate CIE Y/lux.
        z = -0.68202 * r + 0.77073 * g + 0.56332 * b  # Estimate CIE Z.
        total = x + y + z  # Add the color components.

        if total == 0:  # Avoid divide-by-zero in darkness.
            return 0, 0  # Return no color temperature and no lux.

        n = (x / total - 0.3320) / (0.1858 - y / total)  # Calculate McCamy factor.
        cct = 449.0 * n**3 + 3525.0 * n**2 + 6823.3 * n + 5520.33  # Estimate color temperature.
        return cct, y  # Return color temperature and lux-like Y value.

    def threshold(self, cycles=None, min_value=None, max_value=None):
        if cycles is None and min_value is None and max_value is None:  # Read current threshold setup.
            min_value = self._register16(_REGISTER_AILT)  # Read low threshold.
            max_value = self._register16(_REGISTER_AIHT)  # Read high threshold.

            if self._register8(_REGISTER_ENABLE) & _ENABLE_AIEN:  # Check if interrupts are enabled.
                cycles = _CYCLES[self._register8(_REGISTER_APERS) & 0x0F]  # Decode persistence cycles.
            else:  # Interrupts are disabled.
                cycles = -1  # Use -1 to mean disabled.

            return cycles, min_value, max_value  # Return the threshold configuration.

        if min_value is not None:  # Write low threshold when supplied.
            self._register16(_REGISTER_AILT, min_value)  # Store low threshold.

        if max_value is not None:  # Write high threshold when supplied.
            self._register16(_REGISTER_AIHT, max_value)  # Store high threshold.

        if cycles is not None:  # Update interrupt persistence when supplied.
            enable = self._register8(_REGISTER_ENABLE)  # Read current enable flags.

            if cycles == -1:  # Disable interrupts.
                self._register8(_REGISTER_ENABLE, enable & ~_ENABLE_AIEN)  # Clear interrupt enable.
            else:  # Enable interrupts.
                if cycles not in _CYCLES:  # Validate persistence cycles.
                    raise ValueError("invalid persistence cycles")  # Explain invalid input.

                self._register8(_REGISTER_ENABLE, enable | _ENABLE_AIEN)  # Enable interrupts.
                self._register8(_REGISTER_APERS, _CYCLES.index(cycles))  # Store persistence cycles.

    def interrupt(self, value=None):
        if value is None:  # Return interrupt status when no value is supplied.
            return bool(self._register8(_REGISTER_STATUS) & _ENABLE_AIEN)  # Return True/False.

        if value:  # The chip only supports clearing interrupts through this command.
            raise ValueError("interrupt can only be cleared")  # Explain the limitation.

        self.i2c.writeto(self.address, b"\xe6")  # Clear the sensor interrupt.

    def html_rgb(self, data):
        r, g, b, clear = data  # Split raw channels.

        if clear == 0:  # Avoid division by zero in darkness.
            return 0, 0, 0  # Return black.

        red = pow((int((r / clear) * 256) / 255), 2.5) * 255  # Normalize and gamma-correct red.
        green = pow((int((g / clear) * 256) / 255), 2.5) * 255  # Normalize and gamma-correct green.
        blue = pow((int((b / clear) * 256) / 255), 2.5) * 255  # Normalize and gamma-correct blue.

        return min(255, int(red)), min(255, int(green)), min(255, int(blue))  # Clamp to RGB bytes.

    def html_hex(self, data):
        r, g, b = self.html_rgb(data)  # Convert raw channels to RGB bytes.
        return "{0:02x}{1:02x}{2:02x}".format(r, g, b)  # Format as a web-style hex color.

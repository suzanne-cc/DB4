# main.py runs automatically after boot.py on MicroPython boards.

import temp_sensor  # Load the DB4 bioreactor controller module.


temp_sensor.main()  # Start the autonomous controller.

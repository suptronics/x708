#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''' Raspberry Pi x708 Power Management Control

Copyright (C) 2020 Fernando Vano Garcia

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.

                                Fernando Vano Garcia <fernando@fervagar.com>
'''

from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime
from sys import stderr
import subprocess
import gpiozero
import curses
import struct
import smbus
import time
import sys
import os

# --------------------------------------- #
# -- Constants -- #

# Using BCM numbering for GPIO :: https://pinout.xyz/pinout
_GPIO_PIN_PWR_BUTTON = 5    # Physical/Board pin 29
_GPIO_PIN_AC_LOST = 6       # Physical/Board pin 31
_GPIO_PIN_PWR_TRIGGER = 12  # Physical/Board pin 32

I2C_BATTERY_ADDR = 0x36

_RAW_TEMPERATURE_FILE_ = "/sys/class/thermal/thermal_zone0/temp"

# --------------------------------------- #
# -- Lambdas & Types -- #

pos_int = lambda x: int(x) if is_positive_int(x) else raise_ex(
    ArgumentTypeError("'%s' is not a positive int value" % str(x))
)
pos_float = lambda x: float(x) if is_positive_float(x) else raise_ex(
    ArgumentTypeError("'%s' is not a positive float value" % str(x))
)

# --------------------------------------- #
# -- Objects -- #

class NcursesOutput():
    def __init__(self):
        # -- Initialize ncurses -- #
        self._stdscr = curses.initscr()     # initialize curses screen
        curses.curs_set(0)                  # hide cursor
        curses.noecho()                     # turn off auto echoing of keypress on to screen
        curses.cbreak()                     # enter break mode where pressing Enter key
        # after keystroke is not required for it to register
        self._stdscr.keypad(1)              # enable special Key values such as curses.KEY_LEFT etc
        self._stdscr.nodelay(1)             # this will make calls to stdscr.getch() non-blocking

        self._line = 1
        self._rows, self._cols = self._stdscr.getmaxyx()

        # -- Draw a border -- #
        self._stdscr.border(0)

    def cleanup(self):
        self._stdscr.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()

    def set_line(self, line):
        self._line = line

    def print(self, string, row = -1, col = 1, fmt = curses.A_NORMAL):
        if -1 == row:
            row = self._line
            self._line += 1
        self._stdscr.addstr(row, col, string, fmt)

    def draw_hline(self, cstart = 1, cend = -1, row = -1):
        if -1 == row:
            row = self._line
            self._line += 1
        if -1 == cend:
            cend = self._cols - 2
        self._stdscr.hline(row, cstart, curses.ACS_HLINE, cend)

    def refresh(self):
        self._stdscr.refresh()

    def sleep(self, timeout = 0):
        self._stdscr.timeout(timeout)

    def getchar(self):
        return self._stdscr.getch()

# --------------------------------------- #

def error(*msg):
    print(*msg, file=stderr)
    # stderr.flush()


def is_positive_int(n):
    try:
        i = int(n)
        return (i > 0)
    except ValueError:
        return False


def is_positive_float(n):
    try:
        f = float(n)
        return (f > 0)
    except ValueError:
        return False


def raise_ex(e):
    raise e


def open_file(f, p):
    try:
        return open(f, p)
    except IOError as e:
        error("Error opening file '%s': %s" % (f, e.strerror))
        return None

# --------------------------------------- #

def read_temperature(fd):
    try:
        fd.seek(0)
        t = int(fd.readline())
        if not is_positive_int(t):
            raise Exception("Invalid value: '%s'. Aborting." % t)
    except Exception as e:
        error(e)
        return -1

    return (t / 1000)


def read_voltage(bus):
    read = bus.read_word_data(I2C_BATTERY_ADDR, 2)
    swapped = struct.unpack("<H", struct.pack(">H", read))[0]
    voltage = swapped * 1.25 /1000/16
    return voltage


def read_capacity(bus):
    read = bus.read_word_data(I2C_BATTERY_ADDR, 4)
    swapped = struct.unpack("<H", struct.pack(">H", read))[0]
    capacity = swapped/256
    return capacity


def get_params(bus, temperature_fd):
    if temperature_fd is not None:
        temperature = read_temperature(temperature_fd)
    voltage = read_voltage(bus)
    battery = read_capacity(bus)
    timestamp = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
    return (temperature, voltage, battery, timestamp)


def battery_monitor(update_interval, min_voltage, use_ncurses, flag_quiet, flag_watch):
    # 0 = /dev/i2c-0 (port I2C0),
    # 1 = /dev/i2c-1 (port I2C1)
    bus = smbus.SMBus(1)

    temp_fd = open_file(_RAW_TEMPERATURE_FILE_, "r")
    if temp_fd is None:
        print("[!] WARNING: Couldn't open %s" % _RAW_TEMPERATURE_FILE_)

    if (not flag_quiet) and use_ncurses:
        # --- Initialize ncurses --- #
        nco = NcursesOutput()
        nco.print("x708 Monitor", fmt = curses.A_BOLD)
        ui_sec = update_interval / 1000
        ui_sec = ("%d" % ui_sec) if float(ui_sec).is_integer() else ("%.1f" % ui_sec)
        nco.print("Refreshing every %s second%s."
                  % (ui_sec, 's' if update_interval != 1000 else ''))
        nco.print("Press q to exit")

    try:
        while True:
            temp, volt, batt, timestamp = get_params(bus, temp_fd)

            # --- Monitor voltage --- #
            if not flag_watch and (volt < min_voltage):
                msg = "[!] Battery voltage below threshold (%.1fV)." % min_voltage
                msg += " Emergency poweroff."
                #print(msg)
                subprocess.call(['/usr/bin/wall', msg])
                do_shutdown()

            if flag_quiet:
                time.sleep(update_interval / 1000)
                continue

            # --- Print info --- #

            if use_ncurses:
                nco.set_line(5)

                nco.draw_hline()
                nco.print(timestamp)
                nco.draw_hline()

                if temp_fd is not None:
                    nco.print("CPU Temperature: %dºC" % temp)
                nco.print("Voltage: %5.2fV" % volt)
                nco.print("Battery: %5i%%" % batt)

                nco.refresh()
                nco.sleep(update_interval)

                if ord('q') == nco.getchar():
                    return 0

            else:
                # without ncurses
                print(" ---- %s ----" % timestamp)
                if temp_fd is not None:
                    print("CPU Temperature: %dºC" % temp)
                print("Voltage: %5.2fV" % volt)
                print("Battery: %5i%%" % batt)
                print()
                time.sleep(update_interval / 1000)

    except KeyboardInterrupt:
        return 0

    finally:
        if (not flag_quiet) and use_ncurses:
            nco.cleanup()

# --------------------------------------- #


def do_shutdown():
    exit(subprocess.call(['/usr/sbin/poweroff']))


def do_reboot():
    exit(subprocess.call(['/usr/sbin/reboot']))


# --------------------------------------- #
# --- Power Button Callbacks --- #

def pwr_btn_released_callback(pwr_button):
    if not pwr_button.is_held:
        do_reboot()


def pwr_btn_held_callback(pwr_button):
    do_shutdown()


# --------------------------------------- #
# --- Power Loss Detection Callbacks --- #

def ac_power_connected_callback(pld_gpio):
    #print("AC power restored.")
    pass

def ac_power_lost_callback(pld_gpio):
    #print("AC power lost. Running on batteries.")
    pass

# --------------------------------------- #


def main():
    parser = ArgumentParser(description="RPI x708 Power Management Control")
    parser.add_argument("-n", "--interval", type = pos_float, metavar = "seconds", required = False,
                        dest = 'interval', default = 2.0, help = "Specify update interval.")
    parser.add_argument("--min-voltage", type = pos_float, metavar = "volts", required = False,
                        dest = 'min_voltage', default = 3.5,
                        help = "Specify minimum battery voltage (auto-shutdown).")
    parser.add_argument("--ncurses", dest="flag_ncurses", action="store_true",
                        help = "Enable ncurses output.")
    parser.add_argument("-q", "--quiet", dest="flag_quiet", action="store_true",
                        help = "Disable output.")
    parser.add_argument("-w", "--watch", dest="flag_watch", action="store_true",
                        help = "Watch only, without GPIO actuators.")

    parser.set_defaults(flag_ncurses = False)
    parser.set_defaults(flag_quiet = False)
    parser.set_defaults(flag_watch = False)
    args = vars(parser.parse_args())

    if os.geteuid() != 0:
        error("[!] Error: Root privileges are needed to run this script.")
        return -1

    update_interval = args['interval'] * 1000
    min_voltage = args['min_voltage']
    use_ncurses = args['flag_ncurses']
    flag_quiet = args['flag_quiet']
    flag_watch = args['flag_watch']

    if flag_watch and flag_quiet:
        print("[+] Both --watch and --quiet flags are set. Nothing to do.")
        return 0

    if not flag_watch:
        # --- Power Loss Detection --- #
        pld_gpio = gpiozero.DigitalInputDevice(_GPIO_PIN_AC_LOST)

        pld_gpio.when_activated = ac_power_lost_callback
        pld_gpio.when_deactivated = ac_power_connected_callback

        # --- Physical Power Button --- #
        pwr_trigger = gpiozero.DigitalOutputDevice(_GPIO_PIN_PWR_TRIGGER)
        pwr_button = gpiozero.Button(_GPIO_PIN_PWR_BUTTON,
                                     pull_up = False, hold_time = 2)

        pwr_trigger.on()
        if pwr_button.value:
            error("[!] Error: PWR_BUTTON is pulled high. Aborting...")
            return -1

        pwr_button.when_released = pwr_btn_released_callback
        pwr_button.when_held = pwr_btn_held_callback

    # --- Battery Monitor --- #
    if not flag_watch and min_voltage < 3:
        print("[!] WARNING: min_voltage below 3V")
    return battery_monitor(int(update_interval), min_voltage, use_ncurses, flag_quiet, flag_watch)

# --------------------------------------- #


if __name__ == '__main__':
    sys.exit(main())


# --------------------------------------- #

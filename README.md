
# Raspberry Pi x708 Power Management Control

## Description

This tool is a replacement of the original scripts provided by Suptronics for the control of the [x708 expansion board](http://www.suptronics.com/miniPCkits/x708-hardware.html). 
It is coded in python and can be used as a systemd service.

Use the tool at your own risk. I am not part of Suptronics and I am not responsible for any damage that may be caused by the tool or by the hardware.

```
usage: rpi-x708pwm.py [-h] [-n seconds] [--min-voltage volts] [--ncurses] [-q] [-w]

RPI x708 Power Management Control

optional arguments:
  -h, --help            show this help message and exit
  -n seconds, --interval seconds
                        Specify update interval.
  --min-voltage volts   Specify minimum battery voltage (auto-shutdown).
  --ncurses             Enable ncurses output.
  -q, --quiet           Disable output.
  -w, --watch           Watch only, without GPIO actuators.
```


## How to install (as root)

Place the tool in /usr/bin/ and give it execution permissions
```
# cp rpi-x708pwm.py /usr/bin/
# chown root:root /usr/bin/rpi-x708pwm.py
# chmod +x /usr/bin/rpi-x708pwm.py
```



Copy the systemd service unit file & enable it

```
# cp systemd-service/rpi-x708pwm.service /etc/systemd/system/
# systemctl enable rpi-x708pwm.service
```



## Additional notes

### Power physical button timings

The power button timings of the [wiki](http://www.suptronics.com/miniPCkits/x708-hardware.html) do not correspond with my hardware.
For me, the timings are as follows:

| Seconds | Action         |
| ------- | -------------- |
| < 2     | Reboot         |
| 2 - 6   | Shutdown       |
| > 6     | Force Shutdown |



### Shutdown
In order to shutdown x708 unit by hardware, we need to turn on the GPIO PWM1 (pin 13 using BCM numbering, or Physical/Board pin 33). The problem is that it shuts down all the x708 unit, ungratefully. This may lead to problems with the filesystem and SD cards. 
One workaround is to do this just at the last actions performed bysystemd, in `/usr/lib/systemd/system-shutdown/`

However, the files in that directory seems to be executed in parallel. Although this is probably a motive for being slaughtered by
a systemd developer, the workaround I've done is to merge all the files into a single one to make sure that the snippet below is 
executed at the very end. I'm sure there's a better alternative. If you know it and tell me, I'll appreciate it. However, I personally
don't mind too much if it takes a few more seconds to shutdown the pi, so *messirve*.

For more info, see https://www.freedesktop.org/software/systemd/man/systemd-halt.service.html

```
# --> /usr/lib/systemd/system-shutdown/merged.shutdown

# Power off hardware @ x708 power management
# If this code is reached from a normal shutdown/poweroff from software,
# the x708 hard-poweroff performed by using the GPIO 13 works fine. We just
# need to wait for it to complete, which in my rpi is ~5 seconds.
# Even if we sleep for more seconds, the entire x708 hardware shuts down when
# the operation is complete. However, when the x708 button is long-pressed (shutdown),
# this gpio behaves differently for some reason. Therefore, when we shutdown the rpi
# by using the physical button, the following action (GPIO 13) does nothing and 
# the sleep operation is done without interruption. This only affects to the shutdown,
# and the reboot works as normal. This distinction can be checked by reading the value
# of the GPIO 5. Therefore, if its returned value is 1, it means that the physical button
# was pressed, so the whole logic with GPIO 13 should be skipped.

if [ "$1" = "halt" ] || [ "$1" = "poweroff" ]; then
        GPIO_PWR_BUTTON=5
        /usr/bin/echo ${GPIO_PWR_BUTTON} > /sys/class/gpio/export
        echo "in" > /sys/class/gpio/gpio${GPIO_PWR_BUTTON}/direction
        PWR_BUTTON_PRESSED=$(/usr/bin/cat /sys/class/gpio/gpio${GPIO_PWR_BUTTON}/value)

        if [ ${PWR_BUTTON_PRESSED} -eq 0 ]; then
                TIMEOUT=60
                SHUTDOWN=13
                /usr/bin/echo ${SHUTDOWN} > /sys/class/gpio/export
                /usr/bin/echo "out" > /sys/class/gpio/gpio${SHUTDOWN}/direction
                /usr/bin/echo "1" > /sys/class/gpio/gpio${SHUTDOWN}/value

                # Wait for it
                /usr/bin/sleep ${TIMEOUT}
        fi
fi
```
------------------------------------


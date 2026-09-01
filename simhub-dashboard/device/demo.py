"""Synthetic telemetry, so the dashboard has something to show with no PC.

Produces the same protocol lines SimHub sends, driving an imaginary car up
and down the gears.
"""

GEARS = ("1", "2", "3", "4", "5", "6")
MAX_RPM = 8200
IDLE_RPM = 1100
SHIFT_RPM = 7600
TOP_SPEED_PER_GEAR = (60, 100, 145, 190, 235, 280)  # km/h at the shift point


class DemoCar:
    def __init__(self):
        self.gear_index = 0
        self.rpm = IDLE_RPM
        self.accelerating = True

    def step(self, delta_ms):
        step = delta_ms / 1000.0
        if self.accelerating:
            self.rpm += (2600 - self.gear_index * 250) * step
            if self.rpm >= SHIFT_RPM:
                if self.gear_index < len(GEARS) - 1:
                    self.gear_index += 1
                    self.rpm = SHIFT_RPM * 0.72
                else:
                    self.rpm = SHIFT_RPM
                    self.accelerating = False
        else:
            self.rpm -= 2400 * step
            if self.rpm <= IDLE_RPM + 400:
                if self.gear_index > 0:
                    self.gear_index -= 1
                    self.rpm = SHIFT_RPM * 0.65
                else:
                    self.rpm = IDLE_RPM
                    self.accelerating = True

        top = TOP_SPEED_PER_GEAR[self.gear_index]
        bottom = TOP_SPEED_PER_GEAR[self.gear_index - 1] if self.gear_index else 0
        span = (self.rpm - IDLE_RPM) / (SHIFT_RPM - IDLE_RPM)
        speed = bottom + (top - bottom) * max(0.0, min(1.0, span))

        return "$SH|SPD={:.0f}|RPM={:.0f}|MAX={}|GEAR={}".format(
            speed, self.rpm, MAX_RPM, GEARS[self.gear_index]
        )

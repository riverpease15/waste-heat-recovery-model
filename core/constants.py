"""
Shared constants used by both the thermal model and the job optimizer.
"""

# TOU (Time-of-Use) electricity rate schedule — Georgia Power TOU-HLF-16
TOU_ON_PEAK_RATE = 0.175029    # $/kWh
TOU_OFF_PEAK_RATE = 0.050353   # $/kWh
TOU_ON_PEAK_START = 14         # 2 PM
TOU_ON_PEAK_END = 19           # 7 PM

# Rack power baseline
IDLE_RACK_KW = 15.0

# GPU job power tiers (label -> kW per rack)
POWER_LEVELS = {
    "Low (20 kW)": 20.0,
    "Medium (50 kW)": 50.0,
    "High (60 kW)": 60.0,
}


def is_on_peak(hour: float) -> bool:
    """Return True if the given hour (0-24, fractional) falls within on-peak window."""
    return TOU_ON_PEAK_START <= (hour % 24) < TOU_ON_PEAK_END


def tou_rate(hour: float) -> float:
    """Return the TOU electricity rate ($/kWh) for the given hour."""
    return TOU_ON_PEAK_RATE if is_on_peak(hour) else TOU_OFF_PEAK_RATE

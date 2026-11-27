"""Differential duty trim between the two legs.

The inductor sits between the two leg midpoints, so its DC current follows the duty difference
D1 - D2 (27 Nov offset sweep: about -0.02..-0.16 A per 0.001 of duty difference, growing with
the current). Config key "DutyTrimDiff" = D1 - D2 that zeroes the offset (27 Nov: -0.0004),
split symmetrically around the nominal duty so the mean duty is unchanged.
"""

MAX_TRIM = 0.01   # 1 % of duty difference: beyond that it is a typo, not a trim


def leg_duties(duty, trim_diff=0.0, freq=None, max_freq=None):
    """(D1, D2) with D1 - D2 = trim_diff and (D1 + D2) / 2 = duty.
    No trim above max_freq ("DutyTrimMaxFreq"): at 100 kHz 0.0002 per leg is below one timer tick
    (2.9 ns), rounds up to a full tick and overcorrects (27 Nov: -0.03 -> +0.05 A)."""
    trim_diff = float(trim_diff or 0.0)
    if freq is not None and max_freq is not None and freq > max_freq:
        trim_diff = 0.0
    if abs(trim_diff) > MAX_TRIM:
        raise ValueError(f"DutyTrimDiff {trim_diff} exceeds +/-{MAX_TRIM}")
    return round(duty + trim_diff / 2, 6), round(duty - trim_diff / 2, 6)

"""Phase sweep values for the supervisor (no hardware dependency, unit-tested in tests/)."""

import math


def phase_sweep_values(phase_init, phase_final, step, decimals=2):
    """List of phase set-points (degrees) sent by Supervisor.microcontroller_sweep_phase_shift.

    - All-integer inputs (legacy configs): identical to the old
      ``range(phase_init, phase_final + 2, step)``.
    - Any float input (configs from the generator >= ticket #9): PhaseInit, PhaseInit+step, ...
      up to and including PhaseFinal (1e-6 deg tolerance), each rounded to ``decimals``.
      Points are computed as init + k*step (no accumulated float error).
    """
    if step <= 0:
        raise ValueError(f"PhaseStep must be > 0, got {step}")
    if all(isinstance(v, int) for v in (phase_init, phase_final, step)):
        return list(range(phase_init, phase_final + 2, step))
    n = math.floor((phase_final - phase_init) / step + 1e-6)
    return [round(phase_init + k * step, decimals) for k in range(n + 1)]

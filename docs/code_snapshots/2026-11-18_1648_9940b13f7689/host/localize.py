"""3D sound source position from the measured arrival-time differences.

Geometry (metres): origin = centre of the mic square, on the ground; the mics
lie in the z = 0 plane and the source must have z >= 0.

Two estimates are made from the same delays:
  * position (near-field): find s that best explains every pairwise delay
        tau_ij = (|s - m_i| - |s - m_j|) / c
    The wavefront is a sphere, and its curvature across the array tells the
    distance. Curvature shrinks with distance, so range gets unreliable first.
  * direction (far-field): treat the wave as flat,  tau_ij = -(m_i - m_j).u / c
    and solve for the unit vector u. Stays usable much further away.

Why z >= 0 is needed: all mics have z = 0, so a source at (x, y, z) and its
mirror image (x, y, -z) give identical delays. The array cannot tell them
apart; the "nothing below the ground" rule does.
"""

import numpy as np
from scipy.optimize import least_squares

# Mic positions, metres, Mic1..Mic4. Square of side a (h = a/2); each mic stays
# in its quarter when the size changes (10 / 20 / 30 cm):
#   Mic1 (-h, +h)   Mic2 (+h, +h)   Mic3 (+h, -h)   Mic4 (-h, -h)
# Same as the firmware (lib/tdoa/dsp_config.h, "array <cm>" command).
OLD_19CM = np.array([        # the array before 2026-11-16 (other mic order!)
    [0.095, -0.095, 0.0],
    [-0.095, -0.095, 0.0],
    [-0.095, 0.095, 0.0],
    [0.095, 0.095, 0.0],
])


# Measured rotation of the mic square against the axes the source positions are
# measured in. The ESP32 keeps its own copy in flash ("rot" command); bench.py
# reads it from the board. History (docs/experiment_log.md):
#   2026-11-16  +2.13  fitted on the sweeps P1-P4 (4 hand-measured positions)
#   2026-11-18   0.0   fitted on the distance series a30 (-0.15) and a20 (-0.05),
#                      ~2000 chirps at 70+ known points: +2.13 tripled the residual
MEASURED_ROT_DEG = 0.0


def square(side_m, rot_deg=0.0):
    """Mic1 (-h,+h) Mic2 (+h,+h) Mic3 (+h,-h) Mic4 (-h,-h), h = side/2, turned
    rot_deg counter-clockwise (seen from above) about the centre. Same as
    setArrayGeometry() in firmware/lib/tdoa/tdoa.cpp."""
    h = side_m / 2
    m = np.array([[-h, h, 0.0], [h, h, 0.0], [h, -h, 0.0], [-h, -h, 0.0]])
    th = np.radians(rot_deg)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    m[:, :2] = m[:, :2] @ R.T
    return m


MICS = square(0.30)


def set_mics(mics):
    """Change the geometry in place (other modules hold a reference to MICS)."""
    MICS[:] = np.asarray(mics, float)
PAIRS = [(i, j) for i in range(len(MICS)) for j in range(i + 1, len(MICS))]
MAX_RANGE = 6.0              # m; the room is ~5 x 3 x 3 m


def speed_of_sound(temp_c):
    return 331.3 + 0.606 * temp_c


def model_tdoa(s, c, mics=None):
    d = np.linalg.norm((MICS if mics is None else mics) - s, axis=1)
    return np.array([(d[i] - d[j]) / c for i, j in PAIRS])


def pair_delays(arrival):
    """Arrival time per mic -> delay per pair, in PAIRS order."""
    return np.array([arrival[i] - arrival[j] for i, j in PAIRS])


def _grid():
    """Candidate start points spread over the upper half-space."""
    r = np.geomspace(0.15, MAX_RANGE, 14)
    az = np.radians(np.arange(0, 360, 10))
    el = np.radians(np.arange(2, 90, 6))
    R, A, E = np.meshgrid(r, az, el, indexing="ij")
    return np.stack([R * np.cos(E) * np.cos(A), R * np.cos(E) * np.sin(A),
                     R * np.sin(E)], axis=-1).reshape(-1, 3)


GRID = _grid()


def locate(taus, c):
    """Best source position for measured pair delays `taus` (seconds).

    Returns (position [m], rms residual [s]). The grid search picks the right
    "valley" of the error surface, least squares then finds its exact bottom.
    """
    pred = np.array([model_tdoa(g, c) for g in GRID])
    cost = ((pred - taus) ** 2).sum(axis=1)
    best = None
    for k in np.argsort(cost)[:5]:          # refine a few best candidates
        fit = least_squares(lambda s: (model_tdoa(s, c) - taus) * 1e6, GRID[k],
                            bounds=([-MAX_RANGE, -MAX_RANGE, 0],
                                    [MAX_RANGE, MAX_RANGE, MAX_RANGE]))
        if best is None or fit.cost < best.cost:
            best = fit
    rms = np.sqrt(np.mean((model_tdoa(best.x, c) - taus) ** 2))
    return best.x, rms


def direction(taus, c):
    """Far-field direction as (azimuth, elevation) in degrees.

    Linear in u: tau_ij * c = -(m_i - m_j) . u. The mics have no z extent, so
    only u_x and u_y can be solved; u_z follows from |u| = 1 and z >= 0.
    """
    A = np.array([-(MICS[i] - MICS[j])[:2] for i, j in PAIRS])
    uxy, *_ = np.linalg.lstsq(A, np.asarray(taus) * c, rcond=None)
    h = np.linalg.norm(uxy)
    if h > 1:                                # noisy delays can overshoot
        uxy, h = uxy / h, 1.0
    az = np.degrees(np.arctan2(uxy[1], uxy[0])) % 360
    el = np.degrees(np.arccos(h))
    return az, el


def to_spherical(p):
    r = np.linalg.norm(p)
    az = np.degrees(np.arctan2(p[1], p[0])) % 360
    el = np.degrees(np.arcsin(p[2] / r)) if r > 0 else 0.0
    return r, az, el

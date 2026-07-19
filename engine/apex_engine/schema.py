"""Normalized telemetry schema.

Every sim adapter translates its game's raw data into these types.
Units are fixed here and nowhere else:
  speed m/s, distance m, time s, throttle/brake/clutch 0-1, steering -1..1.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(slots=True)
class TelemetryFrame:
    """One sample of normalized telemetry (~50 Hz)."""

    timestamp: float = 0.0        # session elapsed time
    lap_number: int = 0
    lap_time: float = 0.0         # elapsed time on current lap
    lap_dist: float = 0.0         # meters from start/finish line
    pos_x: float = 0.0            # world position (track map)
    pos_y: float = 0.0            # elevation
    pos_z: float = 0.0
    speed: float = 0.0            # m/s
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    steering: float = 0.0         # -1 full left .. +1 full right
    gear: int = 0                 # -1 reverse, 0 neutral
    rpm: float = 0.0
    sector: int = 1               # 1-based current sector
    last_lap_time: float = -1.0   # <0 means none yet
    best_lap_time: float = -1.0
    last_s1: float = -1.0         # last completed lap's sector splits
    last_s2: float = -1.0
    cur_s1: float = -1.0          # current lap's sector splits as they happen
    cur_s2: float = -1.0
    in_pits: bool = False
    # Sim's own lap-legitimacy verdict (rF2 convention):
    # 2 = count lap and time, 1 = count lap not time (cut/reset), 0 = neither.
    count_flag: int = 2
    path_lateral: float = 0.0   # lateral offset from track center path (m)
    track_edge: float = 6.0     # center path -> edge distance, car's side (m)
    abs_active: float = 0.0     # 1.0 while ABS is modulating brake pressure

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SessionContext:
    """Slow-changing session info; sent on connect and on change."""

    game: str = ""
    track: str = ""
    car: str = ""
    car_class: str = ""           # Hyper / LMP2 / GT3 ... PBs group on this
    track_length: float = 0.0     # meters
    session_type: str = ""        # practice / qualifying / race

    def to_dict(self) -> dict:
        return asdict(self)


# Channels stored per lap (parallel arrays sampled together).
LAP_CHANNELS = (
    "lap_time",    # elapsed time within the lap
    "lap_dist",
    "speed",
    "throttle",
    "brake",
    "steering",
    "gear",
    "rpm",
    "pos_x",
    "pos_z",
    "path_lateral",
    "track_edge",
    "abs_active",
)


@dataclass(slots=True)
class LapResult:
    """A completed lap, produced by the recorder."""

    lap_number: int
    lap_time: float
    sector_times: list = field(default_factory=list)  # [s1, s2, s3]
    valid: bool = True
    context: SessionContext = field(default_factory=SessionContext)
    channels: dict = field(default_factory=dict)      # name -> list[float]

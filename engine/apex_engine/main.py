"""Engine entry point.

  python -m apex_engine --adapter sim              # develop without a game
  python -m apex_engine --adapter lmu              # Le Mans Ultimate
  python -m apex_engine --adapter sim --timescale 8 --skill 0.8
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="apex-engine")
    parser.add_argument("--adapter", default="sim", choices=["sim", "lmu"])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--timescale", type=float, default=None,
                        help="sim adapter only: run N x faster than real time")
    parser.add_argument("--skill", type=float, default=None,
                        help="sim adapter only: driver skill 0..1")
    args = parser.parse_args()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.basicConfig(level=logging.INFO)
    root_logger = logging.getLogger()
    for h in root_logger.handlers:
        h.setFormatter(fmt)
    # The engine keeps its own log regardless of how it was launched, so a
    # dead engine always leaves evidence.
    log_dir = Path(args.data_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / "engine.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)

    if args.timescale is not None:
        os.environ["APEX_SIM_TIMESCALE"] = str(args.timescale)
    if args.skill is not None:
        os.environ["APEX_SIM_SKILL"] = str(args.skill)

    from .server import create_app
    import uvicorn

    app = create_app(adapter_name=args.adapter, data_dir=Path(args.data_dir))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

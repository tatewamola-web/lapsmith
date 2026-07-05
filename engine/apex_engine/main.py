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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

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

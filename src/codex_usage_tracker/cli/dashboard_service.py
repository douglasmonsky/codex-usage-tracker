"""CLI adapter for the persistent dashboard service lifecycle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codex_usage_tracker.dashboard_service import (
    dashboard_service_status,
    install_dashboard_service,
    uninstall_dashboard_service,
)


def run_dashboard_service(args: argparse.Namespace) -> int:
    """Run one persistent dashboard service action."""

    home = Path.home()
    if args.service_action == "install":
        status = install_dashboard_service(
            home=home,
            python=Path(sys.executable),
            port=args.port,
        )
        print(f"Dashboard service installed at {status.url}")
        return 0 if status.reachable else 1
    if args.service_action == "status":
        status = dashboard_service_status(home=home)
        if status.reachable:
            print(f"Dashboard service is healthy at {status.url}")
            return 0
        print(f"Dashboard service is {status.detail}; expected {status.url}")
        return 1
    if args.service_action == "uninstall":
        uninstall_dashboard_service(home=home)
        print("Dashboard service uninstalled")
        return 0
    raise ValueError(f"unknown dashboard service action: {args.service_action}")

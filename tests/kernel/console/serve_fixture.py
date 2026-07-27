"""Serve the synthetic K7 console fixture for browser qualification."""

from __future__ import annotations

from codex_usage_tracker.kernel.application import KernelApplication
from codex_usage_tracker.kernel.interfaces.http.server import create_server

from ..interfaces.support import active_runtime, synthetic_sources


def main() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="codex-kernel-console-") as root:
        from pathlib import Path

        application = KernelApplication(
            active_runtime(Path(root)),
            worker_launcher=lambda _paths: None,
            source_provider=lambda _home: synthetic_sources(),
        )
        server = create_server(application, port=8898)
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()

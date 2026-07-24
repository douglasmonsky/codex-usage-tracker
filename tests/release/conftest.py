from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

PACKAGE_STEM = "codex_usage_tracking"
IMPORT_PACKAGE = "codex_usage_tracker"
ASSET_PATH = "plugin_data/dashboard/react/assets/dashboard-react.js"
INDEX_PATH = "plugin_data/dashboard/react/index.html"


class ReleaseFixture:
    def __init__(self, root: Path, *, version: str = "0.23.0") -> None:
        self.root = root
        self.version = version
        self.repo_root = root / "repo"
        self.dist_dir = root / "dist"
        self.manifest_path = root / "release-manifest.json"
        self.asset_bytes = b"console.log('current');\n"
        self.index_bytes = b'<script src="./assets/dashboard-react.js"></script>\n'

    @property
    def wheel_path(self) -> Path:
        return self.dist_dir / f"{PACKAGE_STEM}-{self.version}-py3-none-any.whl"

    @property
    def sdist_path(self) -> Path:
        return self.dist_dir / f"{PACKAGE_STEM}-{self.version}.tar.gz"

    def write_source_assets(
        self,
        *,
        asset_bytes: bytes | None = None,
        index_bytes: bytes | None = None,
    ) -> None:
        package_root = self.repo_root / "src" / IMPORT_PACKAGE
        asset_path = package_root / ASSET_PATH
        index_path = package_root / INDEX_PATH
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(asset_bytes or self.asset_bytes)
        index_path.write_bytes(index_bytes or self.index_bytes)

    def write_distributions(
        self,
        *,
        version: str | None = None,
        wheel_asset: bytes | None = None,
        sdist_asset: bytes | None = None,
    ) -> tuple[Path, Path]:
        selected_version = version or self.version
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        wheel_path = self.dist_dir / f"{PACKAGE_STEM}-{selected_version}-py3-none-any.whl"
        sdist_path = self.dist_dir / f"{PACKAGE_STEM}-{selected_version}.tar.gz"
        wheel_members = {
            f"{IMPORT_PACKAGE}/{INDEX_PATH}": self.index_bytes,
            f"{IMPORT_PACKAGE}/{ASSET_PATH}": wheel_asset or self.asset_bytes,
            (f"{PACKAGE_STEM}-{selected_version}.dist-info/METADATA"): _metadata(selected_version),
        }
        with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
            for name, payload in wheel_members.items():
                wheel.writestr(name, payload)

        root = f"{PACKAGE_STEM}-{selected_version}"
        sdist_members = {
            f"{root}/PKG-INFO": _metadata(selected_version),
            f"{root}/src/{IMPORT_PACKAGE}/{INDEX_PATH}": self.index_bytes,
            f"{root}/src/{IMPORT_PACKAGE}/{ASSET_PATH}": sdist_asset or self.asset_bytes,
        }
        with tarfile.open(sdist_path, "w:gz") as sdist:
            for name, payload in sdist_members.items():
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                info.mtime = 0
                sdist.addfile(info, io.BytesIO(payload))
        return wheel_path, sdist_path


@pytest.fixture
def release_fixture(tmp_path: Path) -> ReleaseFixture:
    fixture = ReleaseFixture(tmp_path)
    fixture.write_source_assets()
    fixture.write_distributions()
    return fixture


def _metadata(version: str) -> bytes:
    return (f"Metadata-Version: 2.4\nName: codex-usage-tracking\nVersion: {version}\n\n").encode()

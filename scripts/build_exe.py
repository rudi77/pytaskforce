#!/usr/bin/env python
"""
Build script for creating the standalone Taskforce Community bundle.

The bundle is a PyInstaller *onedir* tree (``dist/taskforce/``) containing
the unified CLI, the framework, the bundled agent packages and the
compiled web UI. It is what the native installers (``install.sh`` /
``install.ps1``) download in their default "binary" mode.

Usage:
    uv run python scripts/build_exe.py              # full build (UI + freeze)
    uv run python scripts/build_exe.py --skip-ui    # freeze only (UI already built)
    uv run python scripts/build_exe.py --archive    # also pack dist/ into an archive
    uv run python scripts/build_exe.py --clean      # remove build artifacts
    uv run python scripts/build_exe.py --debug      # build with debug info

Requirements:
    uv sync                # installs PyInstaller (dev group) + the project
    Node.js 20+ and pnpm   # only needed unless --skip-ui is passed
"""
import argparse
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

EXE_EXT = ".exe" if sys.platform == "win32" else ""


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent


def clean_build_artifacts(project_root: Path) -> None:
    """Remove build artifacts."""
    print("Cleaning build artifacts...")
    for artifact in ("build", "dist", "__pycache__", "src/taskforce/api/_ui"):
        path = project_root / artifact
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  Removed {artifact}/")
        elif path.exists():
            path.unlink()
            print(f"  Removed {artifact}")
    print("Clean complete.")


def ensure_pyinstaller() -> bool:
    """Ensure PyInstaller is importable."""
    try:
        import PyInstaller  # noqa: F401

        print(f"PyInstaller version: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("PyInstaller not found. Run `uv sync` to install the dev group.")
        return False


def _pnpm_cmd() -> list[str] | None:
    """Return a runnable pnpm command, preferring Corepack."""
    if shutil.which("pnpm"):
        return ["pnpm"]
    if shutil.which("corepack"):
        return ["corepack", "pnpm"]
    return None


def build_ui(project_root: Path) -> bool:
    """Compile the web UI and stage it into the package as ``api/_ui``.

    The frozen app (and the wheel) serve the UI from
    ``src/taskforce/api/_ui``; this mirrors what the Docker image does in
    its ``ui-builder`` stage.
    """
    ui_dir = project_root / "ui"
    if not (ui_dir / "package.json").exists():
        print("No ui/ directory found — skipping web UI build.")
        return True

    pnpm = _pnpm_cmd()
    if pnpm is None:
        print("ERROR: pnpm/corepack not found. Install Node 20+ or pass --skip-ui.")
        return False

    print("Building web UI with pnpm...")
    try:
        if pnpm[0] == "corepack":
            subprocess.run(["corepack", "enable"], cwd=ui_dir, check=False)
        subprocess.run([*pnpm, "install", "--frozen-lockfile"], cwd=ui_dir, check=True)
        subprocess.run([*pnpm, "run", "build"], cwd=ui_dir, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"UI build failed: {exc}")
        return False

    dist = ui_dir / "dist"
    if not (dist / "index.html").exists():
        print("UI build did not produce dist/index.html")
        return False

    target = project_root / "src" / "taskforce" / "api" / "_ui"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(dist, target)
    print(f"  Staged web UI -> {target}")
    return True


def build_executable(project_root: Path, debug: bool = False) -> bool:
    """Freeze the application with PyInstaller using taskforce.spec."""
    if not ensure_pyinstaller():
        return False

    spec_file = project_root / "taskforce.spec"
    if not spec_file.exists():
        print(f"Spec file not found: {spec_file}")
        return False

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
    if debug:
        cmd.append("--debug=all")
    cmd.append(str(spec_file))

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)
    if subprocess.run(cmd, cwd=project_root).returncode != 0:
        print("\nBuild failed!")
        return False

    exe_path = project_root / "dist" / "taskforce" / f"taskforce{EXE_EXT}"
    if not exe_path.exists():
        print(f"Warning: expected executable not found at {exe_path}")
        return False

    print("\n" + "=" * 60)
    print("BUILD SUCCESSFUL!")
    print(f"Bundle: {exe_path.parent}")
    print("\nTesting executable...")
    try:
        result = subprocess.run(
            [str(exe_path), "--help"], capture_output=True, text=True, timeout=60
        )
        print("Test passed: --help works" if result.returncode == 0
              else f"Test warning: --help returned {result.returncode}")
    except Exception as exc:  # pragma: no cover - smoke test only
        print(f"Test warning: could not run executable ({exc})")
    return True


def archive_bundle(project_root: Path) -> bool:
    """Pack dist/taskforce/ into a release archive named per OS/arch."""
    bundle = project_root / "dist" / "taskforce"
    if not bundle.is_dir():
        print("No dist/taskforce/ bundle to archive.")
        return False

    os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower(), platform.machine().lower()
    )
    stem = f"taskforce-community-{os_name}-{arch}"

    if os_name == "windows":
        out = project_root / "dist" / f"{stem}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in bundle.rglob("*"):
                zf.write(item, Path(stem) / item.relative_to(bundle))
    else:
        out = project_root / "dist" / f"{stem}.tar.gz"
        with tarfile.open(out, "w:gz") as tf:
            tf.add(bundle, arcname=stem)

    print(f"Release archive: {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build the Taskforce Community standalone bundle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts and exit")
    parser.add_argument("--skip-ui", action="store_true", help="Skip the web UI build step")
    parser.add_argument("--archive", action="store_true", help="Pack dist/ into a release archive")
    parser.add_argument("--debug", action="store_true", help="Build with debug information")
    args = parser.parse_args()

    project_root = get_project_root()
    print(f"Project root: {project_root}")
    print(f"Python: {sys.executable}\n")

    if args.clean:
        clean_build_artifacts(project_root)
        return 0

    if not args.skip_ui and not build_ui(project_root):
        return 1

    if not build_executable(project_root, debug=args.debug):
        return 1

    if args.archive and not archive_bundle(project_root):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

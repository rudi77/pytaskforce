#!/usr/bin/env python
"""
Build script for creating standalone Taskforce executable.

Usage:
    uv run python scripts/build_exe.py              # Build using spec file (onefile)
    uv run python scripts/build_exe.py --folder     # Build as folder (faster, for testing)
    uv run python scripts/build_exe.py --clean      # Clean build artifacts
    uv run python scripts/build_exe.py --debug      # Build with debug info

Requirements:
    Install dev dependencies first:
        uv sync --extra dev
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent


def clean_build_artifacts(project_root: Path) -> None:
    """Remove build artifacts."""
    print("Cleaning build artifacts...")

    artifacts = ["build", "dist", "__pycache__"]
    for artifact in artifacts:
        path = project_root / artifact
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"  Removed {artifact}/")

    # Also clean spec-generated folders
    for spec_artifact in project_root.glob("*.spec.bak"):
        spec_artifact.unlink()
        print(f"  Removed {spec_artifact.name}")

    print("Clean complete.")


def ensure_pyinstaller() -> bool:
    """Ensure PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("PyInstaller not found. Installing...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Failed to install PyInstaller: {result.stderr}")
            return False
        print("PyInstaller installed successfully.")
        return True


def build_executable(
    project_root: Path,
    use_folder: bool = False,
    debug: bool = False,
) -> bool:
    """
    Build the executable.

    Args:
        project_root: Project root directory
        use_folder: If True, build as folder instead of single file
        debug: If True, include debug information

    Returns:
        True if build succeeded
    """
    if not ensure_pyinstaller():
        return False

    spec_file = project_root / "taskforce.spec"

    if use_folder:
        # Direct PyInstaller invocation for folder build (faster for testing)
        print("Building as folder (faster for testing)...")
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", "taskforce",
            "--console",
            "--noconfirm",
            "--add-data", f"{project_root / 'configs'};configs",
            "--paths", str(project_root / "src"),
        ]

        if debug:
            cmd.append("--debug=all")

        cmd.append(str(project_root / "src" / "taskforce" / "api" / "cli" / "main.py"))
    else:
        # Use spec file for onefile build
        if not spec_file.exists():
            print(f"Spec file not found: {spec_file}")
            print("Creating default spec file...")
            # Fall back to direct invocation
            cmd = [
                sys.executable, "-m", "PyInstaller",
                "--name", "taskforce",
                "--onefile",
                "--console",
                "--noconfirm",
                "--add-data", f"{project_root / 'configs'};configs",
                "--paths", str(project_root / "src"),
                str(project_root / "src" / "taskforce" / "api" / "cli" / "main.py"),
            ]
        else:
            print(f"Building using spec file: {spec_file}")
            cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm"]

            if debug:
                cmd.append("--debug=all")

            cmd.append(str(spec_file))

    print(f"Running: {' '.join(str(c) for c in cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print("\nBuild failed!")
        return False

    # Report output
    print("\n" + "=" * 60)
    dist_path = project_root / "dist"

    if dist_path.exists():
        if use_folder:
            exe_path = dist_path / "taskforce" / "taskforce.exe"
        else:
            exe_path = dist_path / "taskforce.exe"

        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"BUILD SUCCESSFUL!")
            print(f"Executable: {exe_path}")
            print(f"Size: {size_mb:.1f} MB")

            # Test the executable
            print("\nTesting executable...")
            test_result = subprocess.run(
                [str(exe_path), "--help"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if test_result.returncode == 0:
                print("Test passed: --help works correctly")
            else:
                print(f"Test warning: --help returned code {test_result.returncode}")
                if test_result.stderr:
                    print(f"stderr: {test_result.stderr[:500]}")
        else:
            print(f"Warning: Expected executable not found at {exe_path}")
            # List what was created
            print("Contents of dist/:")
            for item in dist_path.iterdir():
                print(f"  {item.name}")
    else:
        print("Warning: dist/ directory not created")

    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build Taskforce standalone executable",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/build_exe.py              # Build single executable
    python scripts/build_exe.py --folder     # Build as folder (faster)
    python scripts/build_exe.py --clean      # Clean build artifacts
    python scripts/build_exe.py --debug      # Build with debug info
        """,
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts and exit",
    )
    parser.add_argument(
        "--folder",
        action="store_true",
        help="Build as folder instead of single file (faster for testing)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Build with debug information",
    )

    args = parser.parse_args()
    project_root = get_project_root()

    print(f"Project root: {project_root}")
    print(f"Python: {sys.executable}")
    print()

    if args.clean:
        clean_build_artifacts(project_root)
        return 0

    success = build_executable(
        project_root,
        use_folder=args.folder,
        debug=args.debug,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

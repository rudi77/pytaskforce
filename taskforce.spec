# taskforce.spec — PyInstaller build spec for the Taskforce Community bundle.
#
# Built via:  uv run python scripts/build_exe.py
#
# Produces a onedir bundle (dist/taskforce/) containing the unified CLI,
# the framework, the bundled agent packages and the compiled web UI.
# The Chromium browser binary is intentionally NOT bundled (too large) —
# users who need the browser tool run `playwright install chromium` once.
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

ROOT = Path(SPECPATH)  # noqa: F821 — SPECPATH is injected by PyInstaller

datas = []
binaries = []
hiddenimports = []

# --- Framework + agent package config trees -------------------------------
_configs = ROOT / "src" / "taskforce" / "configs"
if _configs.is_dir():
    datas += [(str(_configs), "taskforce/configs")]

# Compiled web UI — populated by scripts/build_exe.py before the build.
_ui = ROOT / "src" / "taskforce" / "api" / "_ui"
if _ui.is_dir():
    datas += [(str(_ui), "taskforce/api/_ui")]

for _agent in ("butler", "coding-agent", "rag-agent", "google-workspace"):
    _cfg = ROOT / "agents" / _agent / "configs"
    if _cfg.is_dir():
        datas += [(str(_cfg), f"agents/{_agent}/configs")]

# --- Package metadata so importlib.metadata entry-point discovery works ----
# Taskforce discovers plugins / agent packages / middleware through
# entry points; the frozen app only sees them if their *.dist-info is
# bundled.
for _dist in (
    "taskforce",
    "taskforce-cli",
    "taskforce-butler",
    "taskforce-coding-agent",
    "taskforce-rag-agent",
    "taskforce-google-workspace",
):
    try:
        datas += copy_metadata(_dist)
    except Exception:
        pass

# --- Submodules imported dynamically (entry points, plugins, routers) ------
for _pkg in (
    "taskforce",
    "taskforce_cli",
    "taskforce_butler",
    "taskforce_coding_agent",
    "taskforce_rag_agent",
    "taskforce_google_workspace",
):
    try:
        hiddenimports += collect_submodules(_pkg)
    except Exception:
        pass

# --- Heavy third-party packages with data files / dynamic imports ----------
for _pkg in ("litellm", "docling", "docling_core", "tiktoken", "tiktoken_ext"):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass

# Playwright's Python driver scripts (browser binaries are fetched separately).
try:
    datas += collect_data_files("playwright")
except Exception:
    pass


a = Analysis(  # noqa: F821
    [str(ROOT / "cli" / "src" / "taskforce_cli" / "main.py")],
    pathex=[
        str(ROOT / "src"),
        str(ROOT / "cli" / "src"),
        str(ROOT / "agents" / "butler" / "src"),
        str(ROOT / "agents" / "coding-agent" / "src"),
        str(ROOT / "agents" / "rag-agent" / "src"),
        str(ROOT / "agents" / "google-workspace" / "src"),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff", "black", "PyInstaller"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="taskforce",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="taskforce",
)

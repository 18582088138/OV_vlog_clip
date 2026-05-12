import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

spec_path = Path(globals().get("SPEC") or globals().get("SPECPATH")).resolve()
project_root = spec_path.parent if spec_path.is_file() else spec_path
entry_script = project_root / "ov_video_editing_skills" / "gui" / "launcher.py"
pyinstaller_entry = project_root / "gui_entry.py"

if not entry_script.exists():
    raise FileNotFoundError(f"GUI launcher module not found: {entry_script}")
if not pyinstaller_entry.exists():
    raise FileNotFoundError(f"PyInstaller GUI entry script not found: {pyinstaller_entry}")

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

gui_datas = collect_data_files("ov_video_editing_skills.gui", includes=["default_config.json"])
gui_hiddenimports = sorted(
    set(
        collect_submodules("ov_video_editing_skills.gui")
        + [
            "ov_video_editing_skills.gui.qt_app",
            "ov_video_editing_skills.gui.launcher",
            "ov_video_editing_skills.gui.services",
            "ov_video_editing_skills.gui.settings",
            "ov_video_editing_skills.gui.models",
        ]
    )
)

a = Analysis(
    [str(pyinstaller_entry)],
    pathex=[str(project_root)],
    binaries=[],
    datas=gui_datas,
    hiddenimports=gui_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ov-video-editing-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ov-video-editing-gui",
)
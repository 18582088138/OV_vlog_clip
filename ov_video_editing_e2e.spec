from pathlib import Path

spec_path = Path(globals().get("SPEC") or globals().get("SPECPATH")).resolve()
project_root = spec_path.parent if spec_path.is_file() else spec_path
entry_script = project_root / "ov_video_editing_skills" / "e2e.py"
pyinstaller_entry = project_root / "e2e_entry.py"

if not entry_script.exists():
    raise FileNotFoundError(f"E2E module not found: {entry_script}")
if not pyinstaller_entry.exists():
    raise FileNotFoundError(f"PyInstaller entry script not found: {pyinstaller_entry}")


a = Analysis(
    [str(pyinstaller_entry)],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=["ov_video_editing_skills"],
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
    a.binaries,
    a.datas,
    [],
    name="ov-video-editing-e2e",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
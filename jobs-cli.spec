# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for jobs-cli.

To build locally:
    uv pip install pyinstaller
    uv run pyinstaller jobs-cli.spec

The resulting binary will be in dist/jobs-cli
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Collect all data files and hidden imports for Textual and Rich
textual_datas, textual_binaries, textual_hiddenimports = collect_all('textual')
rich_datas, rich_binaries, rich_hiddenimports = collect_all('rich')

# Collect submodules for our app
app_hiddenimports = collect_submodules('src')

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=textual_binaries + rich_binaries,
    datas=textual_datas + rich_datas,
    hiddenimports=[
        'asyncio',
        'aiosqlite',
        'httpx',
        'pydantic',
        'pydantic_settings',
        'typer',
        'click',
        'mcp',
        *textual_hiddenimports,
        *rich_hiddenimports,
        *app_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='jobs-cli',
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

# -*- mode: python ; coding: utf-8 -*-
# Construction de l'exécutable :  pyinstaller CalculatricePro.spec
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("customtkinter") + collect_data_files("certifi")
datas += [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    excludes=["numpy", "matplotlib", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CalculatricePro",
    console=False,
    icon="assets/icon.ico",
    version="version_info.txt",
    upx=False,
)

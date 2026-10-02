# -*- mode: python ; coding: utf-8 -*-
# Construction de l'exécutable :  pyinstaller --noconfirm --clean CalculatricePro.spec
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("certifi") + [("assets/icon.png", "assets")]

UNUSED_MODULES = [
    "tkinter", "customtkinter", "PIL", "numpy", "pytest",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtXml", "PySide6.QtDBus", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtPdf",
    "PySide6.QtConcurrent", "PySide6.QtPrintSupport", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtDesigner", "PySide6.QtStateMachine",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    excludes=UNUSED_MODULES,
    noarchive=False,
)

# Bibliothèques et extensions Qt dont l'application n'a pas besoin (allège l'exécutable).
UNUSED_FILES = (
    "opengl32sw", "d3dcompiler", "qt6pdf", "qt6qml", "qt6quick", "qt6network",
    "qt6opengl", "qt6virtualkeyboard", "qt6svg", "pyside6/translations/",
    "plugins/imageformats/", "plugins/iconengines/", "plugins/generic/",
    "plugins/networkinformation/", "plugins/tls/", "plugins/styles/",
    "plugins/platforminputcontexts/", "plugins/qmltooling/",
)


def needed(entry):
    name = entry[0].lower().replace("\\", "/")
    return not any(part in name for part in UNUSED_FILES)


a.binaries = [b for b in a.binaries if needed(b)]
a.datas = [d for d in a.datas if needed(d)]

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

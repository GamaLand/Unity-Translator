[app]
title = UnityTranslator
project_dir = tools
input_file = tools/standalone_entry.py
exec_directory = dist/windows
project_file = 
icon =

[python]
packages = Nuitka==4.1.1

[qt]
qml_files = 
excluded_qml_plugins = 
modules = Core,Gui,Widgets
plugins = platforms,styles

[nuitka]
mode = standalone
extra_args = --noinclude-qt-translations --include-package=unitytranslator --include-package-data=unitytranslator --include-package-data=UnityPy --nofollow-import-to=mypy,pytest,ruff --output-filename=UnityTranslator.exe --windows-console-mode=attach --msvc=latest --jobs=4 --assume-yes-for-downloads


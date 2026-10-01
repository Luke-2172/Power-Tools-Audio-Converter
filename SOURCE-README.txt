FNV Audio Converter 1.0 source

Application source: app/
Native launcher and resources: source/
Regression tests: source/tests/
Audit and original instructions are included in this archive.

Run from source with standard Python 3.13 + Tkinter (and requirements.txt for the texture tool):
  python -c "import sys; sys.path.insert(0,'app'); from ui import launch; launch('audio')"

Build the portable release using Python 3.13, Zig 0.13.0, and a runtime folder from the matching release:
  python build_release.py --runtime "path/to/runtime" --zig "path/to/zig"

Runtime libraries keep their own required licenses. Application .pyc files are compiled
Python modules, not encryption or source-code protection. The release does not need this archive.

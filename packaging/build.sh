#!/bin/bash
set -e
python3 -m py_compile src/icons.py
python3 -m py_compile src/config.py
python3 -m py_compile src/display.py
python3 -m py_compile src/input.py
python3 -m py_compile src/cache.py
python3 -m py_compile src/api.py
python3 -m py_compile src/state.py
python3 -m py_compile src/ui.py
python3 -m py_compile src/main.py
python3 -m py_compile src/screens/__init__.py
python3 -m py_compile src/screens/boot.py
python3 -m py_compile src/screens/device_select.py
python3 -m py_compile src/screens/firmware_list.py
python3 -m py_compile src/screens/firmware_detail.py
python3 -m py_compile src/screens/version_select.py
python3 -m py_compile src/screens/cover_view.py
python3 -m py_compile src/flasher.py
python3 -m py_compile src/screens/flash_screen.py
python3 -m py_compile src/screens/tutorial.py
python3 -m py_compile src/screens/file_picker.py
python3 -m py_compile src/screens/file_install.py
echo "Syntax check passed."

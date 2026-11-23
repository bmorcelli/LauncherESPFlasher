"""Thin compatibility shim: keeps `from input import InputHandler,
DevInputHandler` working unchanged for main.py and any other existing
import. The real classes now live in hal/input_backend.py.

InputHandler() with no arguments still works: EvdevKeyboardBackend resolves
kb_device from the active DeviceProfile when none is passed.
"""
from hal.input_backend import EvdevKeyboardBackend as InputHandler
from hal.input_backend import PygameKeyboardBackend as DevInputHandler

#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cache
from screens import boot, tutorial, device_select, firmware_list, firmware_detail, flash_screen


def main():
    from hal.input_facade import build_input_handler
    kbd = build_input_handler()
    kbd.start()

    boot.run(input_handler=kbd)
    kbd.flush()

    if not cache.tutorial_dismissed():
        tutorial.run(input_handler=kbd)
        kbd.flush()

    while True:
        category = device_select.run(input_handler=kbd)
        if category is None:
            break  # ESC → exit app
        kbd.flush()

        while True:
            firmware = firmware_list.run(category, input_handler=kbd)
            if firmware is None:
                break  # ESC → back to device select
            kbd.flush()

            # Inner loop: stay on firmware_detail after download so user can flash next
            while True:
                result = firmware_detail.run(firmware, input_handler=kbd)
                if result is None:
                    break  # ESC → back to firmware list
                kbd.flush()

                action = result.get("_action", "flash")
                if action == "download":
                    flash_screen.run_download(result, input_handler=kbd)
                    kbd.flush()
                    # Re-enter firmware_detail; button now shows FLASH
                else:
                    flash_screen.run(result, input_handler=kbd)
                    kbd.flush()
                    break  # After flash, go back to firmware list

    kbd.stop()


if __name__ == "__main__":
    main()

<div align="center">

<img src="Launcher.png" width="250" alt="Launcher ESP Flasher"/>

# Launcher ESP Flasher

**The easiest way to browse, download and flash ESP32 firmware — right from your CardputerZero.**

[![GitHub stars](https://img.shields.io/github/stars/bmorcelli/LauncherESPFlasher?style=social)](https://github.com/bmorcelli/LauncherESPFlasher)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/release/bmorcelli/LauncherESPFlasher)](https://github.com/bmorcelli/LauncherESPFlasher/releases/latest)

</div>

---

## What is Launcher ESP Flasher?

**Launcher ESP Flasher** is a firmware manager built for the [CardputerZero](https://launcherhub.net) — a Raspberry Pi-based handheld with a keyboard and display. It connects to the **[Launcher Hub](https://launcherhub.net)** catalogue, based on M5Burner with some extra firmware, and lets you browse hundreds of community firmwares for M5Stack devices, filter and sort them, preview cover art, pick the exact version you want, and flash straight to any connected ESP32 — all without touching a PC.

No drivers. No scripts. No terminal. Just scroll, select, and flash.

> Part of the **[Launcher](https://github.com/bmorcelli/Launcher)** ecosystem — the open AppStore for M5Stack devices.

---

## Features at a Glance

- Browse the full **[LauncherHub](https://launcherhub.net)** catalogue of ESP32 firmwares
- Filter by device category and search by name in real time
- Sort by downloads, release date, or name
- Preview cover images for each firmware
- Select any specific version before flashing
- Flash directly via USB — download and write in one step
- **Offline / local file mode** — flash any `.bin` file from your filesystem without internet

---

<details>
  <summary><h3>Screenshots</h3></summary>

### Boot Screen

<div align="center">
<img src="assets/screenshots/00 bootscreen.png" width="400" alt="Boot Screen"/>
</div>

---

### Device Selection

Browse devices by category. Sort by **Name** or **Count** (number of available firmwares). Type any letter to filter live.

<div align="center">
<img src="assets/screenshots/01 main_name.png" width="400" alt="Device select — sorted by name"/>
<img src="assets/screenshots/02 main_cnt.png" width="400" alt="Device select — sorted by count"/>
</div>

<div align="center">
<img src="assets/screenshots/05 main_filter.png" width="400" alt="Device filter active"/>
</div>

---

### Firmware List

Once you select a device, the firmware catalogue loads. Sort by **Downloads**, **Date**, or **Name**. Type to filter by firmware name.

<div align="center">
<img src="assets/screenshots/17 firmware_DL.png" width="400" alt="Firmware list — sorted by downloads"/>
<img src="assets/screenshots/19 firmware_NAME.png" width="400" alt="Firmware list — sorted by name"/>
</div>

<div align="center">
<img src="assets/screenshots/20 firmware_filter.png" width="400" alt="Firmware list — filter active"/>
</div>

---

### Firmware Detail

Tap into any firmware to read its description, see the download count, and access three actions:

| Button | Action |
|--------|--------|
| **Cover** | View the firmware's cover image (green when available) |
| **Version** | Pick a specific release version |
| **Download** | Download and flash to the connected ESP32 |

<div align="center">
<img src="assets/screenshots/21 firmware_detail.png" width="400" alt="Firmware detail"/>
<img src="assets/screenshots/23 firmware_detail_coverimg.png" width="400" alt="Cover image view"/>
</div>

<div align="center">
<img src="assets/screenshots/25 firmware_detail_version_pick.png" width="400" alt="Version selection"/>
</div>

---

### Online Flash

Download and flash happens in one seamless step. A progress bar shows the flash percentage in real time.

<div align="center">
<img src="assets/screenshots/28 firmware_flash_progress2.png" width="400" alt="Flashing in progress"/>
<img src="assets/screenshots/29 firmware_flash_done.png" width="400" alt="Flash complete"/>
</div>

---

### Local File Install

Press the **folder icon** on any screen to install a `.bin` file directly from the filesystem — no internet required.

The app detects the connected ESP32, browses your filesystem, and handles both merged binaries and multi-part firmwares automatically.

<div align="center">
<img src="assets/screenshots/11 file_esp_detection.png" width="400" alt="ESP32 detection"/>
<img src="assets/screenshots/13 file_firmware_pick.png" width="400" alt="Filesystem browser"/>
</div>

**Merged binary** — one file flashed to address `0x0`:

<div align="center">
<img src="assets/screenshots/14 file_install_merged.png" width="400" alt="Merged binary install prompt"/>
</div>

**Partial / app-only binary** — choose bundled bootloader + partition table or supply your own custom files:

<div align="center">
<img src="assets/screenshots/15 file_install_multipart.png" width="400" alt="Multipart install mode selection"/>
<img src="assets/screenshots/16 file_install_multipart_detail.png" width="400" alt="Custom multipart install screen"/>
</div>

---

## Navigation

Launcher ESP Flasher is fully keyboard-driven, designed for the CardputerZero physical keyboard.

| Action | Key |
|--------|-----|
| Move up / down | `FN + F` / `FN + X` |
| Previous page / back | `FN + Z` |
| Next page / forward | `FN + C` |
| Confirm / select | `Enter` |
| Cancel / go back | `Escape` |
| Switch focus between controls | `Tab` |
| Type to filter | Any printable key (in list screens) |

---

</details>

## Installation

Download the latest `.deb` from the [Releases](https://github.com/bmorcelli/LauncherESPFlasher/releases) page and install it on your CardputerZero:

```bash
wget https://github.com/bmorcelli/LauncherESPFlasher/releases/download/0.0.3/launcherespflasher_0.0.3_arm64.deb
sudo apt install ./launcherespflasher_0.0.3_arm64.deb
# Open Launcher ESP Flasher from the AppLauncher icon, otherwise it won't work.
```

The app will appear automatically in the Launcher app menu.

---

## Related Projects

- **[Launcher](https://github.com/bmorcelli/Launcher)** — The CardputerZero app launcher and AppStore
- **[LauncherHub](https://launcherhub.net)** — The community firmware catalogue this app connects to

---

## Support the Project

If Launcher ESP Flasher saved you time or helped you discover awesome firmwares, consider buying me a coffee — it keeps the project alive and growing!

<div align="center">

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-%E2%98%95-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/bmorcelliz)

<a href="https://buymeacoffee.com/bmorcelliz" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="200"/>
</a>

</div>

You can also **[sponsor this project on GitHub](https://github.com/sponsors/bmorcelli)** — every contribution helps!

---

<div align="center">

Made with passion for the M5Stack community · [LauncherHub](https://launcherhub.net) · [GitHub](https://github.com/bmorcelli/LauncherESPFlasher)

</div>

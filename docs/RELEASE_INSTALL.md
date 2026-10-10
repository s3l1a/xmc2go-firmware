# Install a release on an XMC 2Go board

These binaries target the Infineon XMC 2Go kit with an XMC1100-Q024F0032 (or
larger compatible XMC1100), the onboard J-Link debugger, and the board LED/UART
connections described in `DESIGN.md`.

## Safety first

* Never erase or program `0x10000000..0x10000FFF`. This is configuration sector
  CS0 and contains the BMI. Changing it can disable debug access.
* This is development-board firmware, not a secure production updater. Images
  use CRC integrity checks but are not signed or authenticated. Anyone with
  serial access can request an update.
* `app_bad_*` and `app_crash_*` are intentional rollback tests. They reset or
  fault by design. Use `app_traffic_*` for normal operation.
* Keep the board connected to stable USB power while initially installing the
  bootloader.

## Requirements

1. Windows with Python 3.8 or newer.
2. SEGGER J-Link software and the J-Link-OB CDC USB driver.
3. An XMC 2Go board connected by USB.

No Python packages are required. The updater uses the Windows COM API directly;
`pyserial` is optional.

## First installation

1. Extract the release ZIP.
2. Open J-Link Commander and select device `XMC1100-Q024x0032`, interface SWD,
   and speed 4000 kHz.
3. Program `dist/bootloader.bin` as a raw binary at address `0x10001000`.
4. Do not use BMI programming and do not perform a whole-chip erase.
5. Reset the board. The bootloader waits in recovery mode if no valid app is
   installed.

J-Link Commander commands, after adapting the extracted path:

```text
device XMC1100-Q024x0032
si swd
speed 4000
connect
loadbin C:\path\to\xmc2go-firmware-v1.0.0\dist\bootloader.bin, 0x10001000
r
g
exit
```

## Install the traffic-light app

1. Double-click `Start GUI.bat`.
2. Select the XMC 2Go J-Link virtual COM port and click **Connect**.
3. Browse to `dist/app_traffic_A.img` or `dist/app_traffic_B.img`. Choose the
   image for the inactive slot shown by the GUI.
4. Click **Update** and wait for verification and reboot to complete.

The CLI provides the same flow:

```bat
"XMC 2Go CLI.bat" list
"XMC 2Go CLI.bat" --port COM4 info
"XMC 2Go CLI.bat" --port COM4 update dist\app_traffic_B.img
```

Replace `COM4` and the A/B image with values reported on your computer. If the
app is already running, press RESET while the updater is connecting or send
`X` over the serial port to reopen the bootloader window.

## Included images

| File | Purpose |
|---|---|
| `dist/bootloader.bin` | Raw bootloader for address `0x10001000` |
| `dist/app_traffic_A.img` | Normal traffic-light app for slot A |
| `dist/app_traffic_B.img` | Normal traffic-light app for slot B |
| `dist/app_bad_A.img`, `dist/app_bad_B.img` | Intentional watchdog rollback tests |
| `dist/app_crash_A.img`, `dist/app_crash_B.img` | Intentional HardFault rollback tests |
| `SHA256SUMS.txt` | SHA-256 checksums for release files |

Board-specific factory backups are deliberately not distributed.

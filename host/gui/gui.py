#!/usr/bin/env python3
"""xmc2go updater GUI (Tkinter, stdlib only).

- Lists COM ports (best-effort XMC 2Go / J-Link VCP highlight)
- Connect/disconnect, device status panel, image file selection with host-side
  header validation, Update with progress bar and cancel, Rollback, Reboot
- All serial I/O runs in a worker thread; results are posted to the Tk main
  loop through a queue (the UI thread never blocks)
- Uses pyserial when installed, otherwise the stdlib Win32 COM backend
"""
import os
import queue
import struct
import sys
import threading
import traceback

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    print("tkinter is not available in this Python installation")
    sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "updater"))

from xmcup.transport import open_serial, list_ports
from xmcup.protocol import Client, ProtocolError, DeviceStatus
from xmcup.update import run_update, pick_target_slot, UpdateError, slot_start
from xmcup.image import (parse_image_header, check_image, build_image,
                         ImageError, IMAGE_HEADER_SIZE)
from xmcup.framing import STATUS_NAMES

STATE_NAMES = {0: "invalid", 1: "valid", 2: "trial", 3: "bad"}


class App(object):
    def __init__(self, root):
        self.root = root
        self.root.title("XMC 2Go updater")
        self.q = queue.Queue()
        self.serial = None
        self.client = None
        self.worker = None
        self.cancel_flag = threading.Event()
        self.hex_log = tk.BooleanVar(value=False)
        self.image_path = tk.StringVar()
        self.image_info = tk.StringVar(value="no image selected")
        self.status_vars = {
            "bl": tk.StringVar(value="-"),
            "active": tk.StringVar(value="-"),
            "a": tk.StringVar(value="-"),
            "b": tk.StringVar(value="-"),
            "attempts": tk.StringVar(value="-"),
        }
        self._build_ui()
        self.root.after(100, self._poll)
        self.refresh_ports()

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(top, text="Port").grid(row=row, column=0, sticky="w")
        self.port_combo = ttk.Combobox(top, width=40, state="readonly")
        self.port_combo.grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Button(top, text="Refresh", command=self.refresh_ports).grid(
            row=row, column=2, padx=2)
        self.connect_btn = ttk.Button(top, text="Connect",
                                      command=self.toggle_connect)
        self.connect_btn.grid(row=row, column=3, padx=2)

        row += 1
        status = ttk.LabelFrame(top, text="Device status", padding=6)
        status.grid(row=row, column=0, columnspan=4, sticky="ew", pady=6)
        for i, (key, label) in enumerate((
                ("bl", "Bootloader"), ("active", "Active slot"),
                ("a", "Slot A"), ("b", "Slot B"),
                ("attempts", "Boot attempts"))):
            ttk.Label(status, text=label + ":").grid(row=i // 3,
                                                     column=(i % 3) * 2,
                                                     sticky="w", padx=2)
            ttk.Label(status, textvariable=self.status_vars[key],
                      width=28).grid(row=i // 3, column=(i % 3) * 2 + 1,
                                     sticky="w", padx=2)
        ttk.Button(status, text="Refresh status",
                   command=self.refresh_info).grid(row=0, column=6, rowspan=2)

        row += 1
        img = ttk.LabelFrame(top, text="Application image", padding=6)
        img.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4)
        img.columnconfigure(1, weight=1)
        ttk.Button(img, text="Browse...", command=self.browse_image).grid(
            row=0, column=0, padx=2)
        ttk.Entry(img, textvariable=self.image_path).grid(row=0, column=1,
                                                          sticky="ew", padx=4)
        ttk.Label(img, textvariable=self.image_info).grid(row=1, column=0,
                                                          columnspan=3,
                                                          sticky="w", padx=2)

        row += 1
        actions = ttk.Frame(top)
        actions.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4)
        self.update_btn = ttk.Button(actions, text="Update",
                                     command=self.start_update,
                                     state="disabled")
        self.update_btn.grid(row=0, column=0, padx=2)
        self.cancel_btn = ttk.Button(actions, text="Cancel",
                                     command=self.cancel_update,
                                     state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=2)
        ttk.Button(actions, text="Rollback",
                   command=self.start_rollback).grid(row=0, column=2, padx=2)
        ttk.Button(actions, text="Reboot",
                   command=self.start_reboot).grid(row=0, column=3, padx=2)

        row += 1
        self.progress = ttk.Progressbar(top, maximum=1.0)
        self.progress.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4)

        row += 1
        logf = ttk.LabelFrame(top, text="Log", padding=4)
        logf.grid(row=row, column=0, columnspan=4, sticky="nsew")
        top.rowconfigure(row, weight=1)
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.log = tk.Text(logf, height=14, width=80, state="disabled",
                           wrap="none")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        ttk.Checkbutton(logf, text="full hex dumps",
                        variable=self.hex_log).grid(row=1, column=0,
                                                    sticky="w")

    # ---------------- logging ----------------
    def append_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def link_log(self, msg):
        if self.hex_log.get():
            self.append_log("  [link] " + msg)

    # ---------------- ports / connection ----------------
    def refresh_ports(self):
        try:
            ports = list_ports()
        except Exception as exc:
            self.append_log("port enumeration failed: %s" % exc)
            ports = []
        values = []
        self._port_desc = {}
        for p in ports:
            desc = p.get("description") or ""
            mark = ""
            if any(k in desc.lower() for k in ("j-link", "xmc", "cdc",
                                               "segger")):
                mark = "  <- likely XMC 2Go / J-Link VCP"
            values.append("%s%s" % (p["port"], mark))
            self._port_desc[p["port"]] = desc
        self.port_combo["values"] = values
        if values:
            self.port_combo.current(0)
        self.append_log("found %d port(s)" % len(values))

    def selected_port(self):
        sel = self.port_combo.get()
        return sel.split()[0] if sel else None

    def toggle_connect(self):
        if self.client is not None:
            self._disconnect()
            return
        port = self.selected_port()
        if not port:
            messagebox.showwarning("no port", "select a COM port first")
            return
        self.connect_btn.configure(state="disabled")
        self.append_log("connecting to %s ..." % port)

        def work():
            try:
                ser = open_serial(port, baudrate=115200, timeout=2.0)
                ser.open()
                client = Client(ser, timeout=2.0, on_log=lambda m:
                                self.q.put(("linklog", m)),
                                cancel=self.cancel_flag.is_set)
                ping = client.ping()
                return ("connected", ser, client, ping)
            except Exception as exc:
                return ("connect_failed", str(exc))

        self._run_worker(work, self._on_connected)

    def _on_connected(self, result):
        self.connect_btn.configure(state="normal")
        if result[0] != "connected":
            self.append_log("connect failed: %s" % result[1])
            return
        _, self.serial, self.client, ping = result
        self.connect_btn.configure(text="Disconnect")
        self.update_btn.configure(state="normal")
        self.append_log("connected: bootloader %d.%d.%d (proto v%d)"
                        % (ping["bl_version"] + (ping["proto_version"],)))
        self.refresh_info()

    def _disconnect(self):
        try:
            if self.serial:
                self.serial.close()
        finally:
            self.serial = None
            self.client = None
            self.connect_btn.configure(text="Connect")
            self.update_btn.configure(state="disabled")
            self.append_log("disconnected")

    def refresh_info(self):
        if self.client is None:
            return

        def work():
            info = self.client.info()
            return ("info", info)

        self._run_worker(work, self._on_info)

    def _on_info(self, result):
        if result[0] != "info":
            self.append_log("info failed: %s" % result[1])
            return
        info = result[1]
        self.status_vars["bl"].set("%d.%d.%d" % info.bl_version)
        self.status_vars["active"].set("AB"[info.active_slot])
        self.status_vars["a"].set("%s  v%d.%d.%d b%d" % (
            STATE_NAMES.get(info.slot_a_state, "?"), info.slot_a_version[0],
            info.slot_a_version[1], info.slot_a_version[2],
            info.slot_a_version[3]))
        self.status_vars["b"].set("%s  v%d.%d.%d b%d" % (
            STATE_NAMES.get(info.slot_b_state, "?"), info.slot_b_version[0],
            info.slot_b_version[1], info.slot_b_version[2],
            info.slot_b_version[3]))
        self.status_vars["attempts"].set(str(info.boot_attempts))
        self.append_log("status: active=%s A=%s B=%s attempts=%d"
                        % ("AB"[info.active_slot],
                           STATE_NAMES.get(info.slot_a_state),
                           STATE_NAMES.get(info.slot_b_state),
                           info.boot_attempts))

    # ---------------- image ----------------
    def browse_image(self):
        path = filedialog.askopenfilename(
            title="Select application image",
            filetypes=[("XMC images", "*.img"), ("Binaries", "*.bin"),
                       ("All files", "*.*")])
        if not path:
            return
        self.image_path.set(path)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            self.image_info.set("cannot read file: %s" % exc)
            self.update_btn.configure(state="disabled")
            return
        try:
            if data[:4] == b"XCM1":
                hdr = parse_image_header(data)
                # validate against both slots (header tells the real one)
                start = slot_start(hdr.slot_id)
                check_image(data, start, 0x2000, hdr.slot_id)
                self._image_slot = hdr.slot_id
                self.image_info.set(
                    "image OK: v%d.%d.%d build %d, slot %s, %d bytes"
                    % (hdr.ver_major, hdr.ver_minor, hdr.ver_patch,
                       hdr.build_number, "AB"[hdr.slot_id], len(data)))
                self._image = data
            else:
                self.image_info.set(
                    "raw .bin (%d bytes) - version is assigned on update"
                    % len(data))
                self._image = data
                self._image_slot = None
            if self.client is not None:
                self.update_btn.configure(state="normal")
        except ImageError as exc:
            self.image_info.set("INVALID image: %s" % exc)
            self._image = None
            self.update_btn.configure(state="disabled")

    # ---------------- update flow ----------------
    def start_update(self):
        data = getattr(self, "_image", None)
        if not data or self.client is None:
            return
        self.cancel_flag.clear()
        self.update_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.append_log("update starting...")

        def work():
            info = self.client.info()
            slot = getattr(self, "_image_slot", None)
            if slot is None:
                slot, reason = pick_target_slot(info)
                self.q.put(("log", "target slot %s (%s)" % ("AB"[slot], reason)))
                # raw bin: build header now
                ver = (1, 0, 0, 0)
                image = build_image(data, slot_start(slot), 0x2000, slot,
                                    ver=ver, build_number=0)
            else:
                image = data
            run_update(self.client, image, slot,
                       progress=lambda f, m: self.q.put(("progress", (f, m))),
                       cancel=self.cancel_flag.is_set, boot=True)
            return ("update_done", slot)

        self._run_worker(work, self._on_update_done)

    def _on_update_done(self, result):
        self.cancel_btn.configure(state="disabled")
        self.update_btn.configure(state="normal")
        if result[0] != "update_done":
            self.append_log("update FAILED: %s" % result[1])
            self.append_log("device state unchanged (old slot still active)")
            messagebox.showerror("update failed", str(result[1]))
            return
        self.append_log("update complete: slot %s installed (trial), rebooting"
                        % "AB"[result[1]])
        self.root.after(2000, self.refresh_info)

    def cancel_update(self):
        self.cancel_flag.set()
        self.append_log("cancel requested (old slot stays active)")

    def start_rollback(self):
        if self.client is None:
            return
        self.append_log("rollback requested")

        def work():
            self.client.rollback()
            return ("rollback_done",)

        self._run_worker(work, lambda r: self.append_log(str(r)))

    def start_reboot(self):
        if self.client is None:
            return
        self.append_log("reboot requested")

        def work():
            self.client.boot()
            return ("reboot_done",)

        self._run_worker(work, lambda r: self.append_log(str(r)))

    # ---------------- worker plumbing ----------------
    def _run_worker(self, fn, on_done):
        def runner():
            try:
                result = fn()
            except (ProtocolError, DeviceStatus, UpdateError, ImageError) as exc:
                result = ("error", str(exc))
            except Exception as exc:  # keep the UI alive no matter what
                result = ("error", "internal: %s\n%s"
                          % (exc, traceback.format_exc()))
            self.q.put(("done", (on_done, result)))

        self.worker = threading.Thread(target=runner, daemon=True)
        self.worker.start()

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.append_log(payload)
                elif kind == "linklog":
                    self.link_log(payload)
                elif kind == "progress":
                    frac, msg = payload
                    self.progress["value"] = frac
                    self.append_log("[%3d%%] %s" % (int(frac * 100), msg))
                elif kind == "done":
                    on_done, result = payload
                    if on_done:
                        on_done(result)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

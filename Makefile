# XMC 2Go custom bootloader, apps and host tools.
#
# Target build:   make            (needs arm-none-eabi-gcc, see tools/setup_toolchain.md)
# Host tests:     make host-test  (Python unittest + host C tests)
# Images:         make images     (build/*.img ready for the updater)
#
# If GNU make is unavailable, tools/build_fw.py performs the same firmware
# build steps (verified with arm-none-eabi-gcc 14.3).

CROSS   ?= arm-none-eabi-
CC      := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
SIZE    := $(CROSS)size
PYTHON  ?= python

BUILD   := build
DIST    := dist

CPUFLAGS := -mcpu=cortex-m0 -mthumb
CFLAGS  := $(CPUFLAGS) -std=c11 -Os -g3 -Wall -Wextra \
           -ffunction-sections -fdata-sections -fno-strict-aliasing \
           -Icommon -Iboard
ASFLAGS := $(CPUFLAGS) -x assembler-with-cpp -Icommon -Iboard
LDFLAGS := $(CPUFLAGS) -nostartfiles -Wl,--gc-sections -Wl,--print-memory-usage

# ---- sources ----
BOARD_SRC_C := board/system.c board/uart.c board/led.c board/wdt.c \
               board/flash.c board/meta.c board/delay.c
BOARD_SRC_S := board/startup.S
COMMON_SRC  := common/crc16.c common/crc32.c
APP_SRC_C   := board/timer.c board/app_api.c

BOARD_OBJ := $(patsubst %.c,$(BUILD)/%.o,$(BOARD_SRC_C)) \
             $(patsubst %.S,$(BUILD)/%.o,$(BOARD_SRC_S))
COMMON_OBJ := $(patsubst %.c,$(BUILD)/%.o,$(COMMON_SRC))
APP_OBJ := $(patsubst %.c,$(BUILD)/%.o,$(APP_SRC_C))

BOOT_OBJ := $(BUILD)/bootloader/main.o $(BUILD)/bootloader/proto.o
TRAFFIC_OBJ := $(BUILD)/app_traffic/main.o $(BUILD)/app_traffic/traffic_fsm.o
BAD_OBJ := $(BUILD)/app_bad/main.o
CRASH_OBJ := $(BUILD)/app_crash/main.o

ELFS := $(BUILD)/bootloader.elf \
        $(BUILD)/app_traffic_A.elf $(BUILD)/app_traffic_B.elf \
        $(BUILD)/app_bad_A.elf $(BUILD)/app_bad_B.elf \
        $(BUILD)/app_crash_A.elf $(BUILD)/app_crash_B.elf

.PHONY: all clean images host-test host-test-python host-test-c host-test-fsm size

all: $(ELFS) size

# ---- generic compile rules ----
$(BUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: %.S
	@mkdir -p $(dir $@)
	$(CC) $(ASFLAGS) -c $< -o $@

# ---- link rules ----
$(BUILD)/bootloader.elf: $(BOOT_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_bootloader.ld
	$(CC) $(LDFLAGS) -T board/link_bootloader.ld \
		$(BOOT_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/bootloader.map
	$(OBJCOPY) -O binary $@ $(BUILD)/bootloader.bin
	@mkdir -p $(DIST)
	cp $(BUILD)/bootloader.bin $(DIST)/bootloader.bin

$(BUILD)/app_traffic_A.elf: $(TRAFFIC_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_slotA.ld
	$(CC) $(LDFLAGS) -T board/link_slotA.ld \
		$(TRAFFIC_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/app_traffic_A.map
	$(OBJCOPY) -O binary $@ $(BUILD)/app_traffic_A.bin

$(BUILD)/app_traffic_B.elf: $(TRAFFIC_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_slotB.ld
	$(CC) $(LDFLAGS) -T board/link_slotB.ld \
		$(TRAFFIC_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/app_traffic_B.map
	$(OBJCOPY) -O binary $@ $(BUILD)/app_traffic_B.bin

$(BUILD)/app_bad_A.elf: $(BAD_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_slotA.ld
	$(CC) $(LDFLAGS) -T board/link_slotA.ld \
		$(BAD_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/app_bad_A.map
	$(OBJCOPY) -O binary $@ $(BUILD)/app_bad_A.bin

$(BUILD)/app_bad_B.elf: $(BAD_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_slotB.ld
	$(CC) $(LDFLAGS) -T board/link_slotB.ld \
		$(BAD_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/app_bad_B.map
	$(OBJCOPY) -O binary $@ $(BUILD)/app_bad_B.bin

$(BUILD)/app_crash_A.elf: $(CRASH_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_slotA.ld
	$(CC) $(LDFLAGS) -T board/link_slotA.ld \
		$(CRASH_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/app_crash_A.map
	$(OBJCOPY) -O binary $@ $(BUILD)/app_crash_A.bin

$(BUILD)/app_crash_B.elf: $(CRASH_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) board/link_slotB.ld
	$(CC) $(LDFLAGS) -T board/link_slotB.ld \
		$(CRASH_OBJ) $(APP_OBJ) $(BOARD_OBJ) $(COMMON_OBJ) -o $@ \
		-Wl,-Map=$(BUILD)/app_crash_B.map
	$(OBJCOPY) -O binary $@ $(BUILD)/app_crash_B.bin

size: $(ELFS)
	@for f in $(ELFS); do $(SIZE) $$f; done

# ---- images for the host updater ----
images: all
	@mkdir -p $(DIST)
	$(PYTHON) tools/mkimage.py --slot 0 --bin $(BUILD)/app_traffic_A.bin --out $(DIST)/app_traffic_A.img --ver 1.0.0 --build 1
	$(PYTHON) tools/mkimage.py --slot 1 --bin $(BUILD)/app_traffic_B.bin --out $(DIST)/app_traffic_B.img --ver 1.0.0 --build 1
	$(PYTHON) tools/mkimage.py --slot 0 --bin $(BUILD)/app_bad_A.bin     --out $(DIST)/app_bad_A.img     --ver 0.0.1 --build 1
	$(PYTHON) tools/mkimage.py --slot 1 --bin $(BUILD)/app_bad_B.bin     --out $(DIST)/app_bad_B.img     --ver 0.0.1 --build 1
	$(PYTHON) tools/mkimage.py --slot 0 --bin $(BUILD)/app_crash_A.bin   --out $(DIST)/app_crash_A.img   --ver 0.0.2 --build 1
	$(PYTHON) tools/mkimage.py --slot 1 --bin $(BUILD)/app_crash_B.bin   --out $(DIST)/app_crash_B.img   --ver 0.0.2 --build 1
	@echo "images in $(DIST)/"

# ---- host tests (no hardware) ----
host-test: host-test-python host-test-c host-test-fsm

host-test-python:
	$(PYTHON) -m unittest discover -s tests/host_unit -v

host-test-c:
	tests/host_unit/run_c_vectors.bat

host-test-fsm:
	tests/host_fsm/run.bat

clean:
	$(PYTHON) -c "import shutil; shutil.rmtree('$(BUILD)', ignore_errors=True); shutil.rmtree('$(DIST)', ignore_errors=True); print('cleaned')"

/*
 * link_bootloader.ld - bootloader image at 0x10001000 (8 KB).
 *
 * XMC1100 specifics (RM 2.5.4.1, 18.1.3):
 *  - SSW loads SP from 0x10001000 and jumps to *(0x10001004).
 *  - CLK_VAL1/CLK_VAL2 words follow in the vector table.
 *  - .XmcVeneerCode runs at 0x2000000C (ROM vector table targets), stored in
 *    flash and copied by Reset_Handler.
 */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x10001000, LENGTH = 8K
  VENEER (rw) : ORIGIN = 0x2000000C, LENGTH = 0x1F4
  RAM (rwx)   : ORIGIN = 0x20000200, LENGTH = 16K - 0x200
}

ENTRY(Reset_Handler)

SECTIONS
{
  .isr_vector :
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .text :
  {
    *(.text*)
    *(.rodata*)
    . = ALIGN(4);
  } > FLASH

  .VENEER_Code :
  {
    . = ALIGN(4);
    VeneerStart = .;
    KEEP(*(.XmcVeneerCode))
    . = ALIGN(4);
    VeneerEnd = .;
  } > VENEER AT > FLASH

  VeneerLoadAddr = LOADADDR(.VENEER_Code);

  .data :
  {
    . = ALIGN(4);
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > RAM AT > FLASH

  _sidata = LOADADDR(.data);

  .bss (NOLOAD) :
  {
    . = ALIGN(4);
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > RAM

  . = ALIGN(8);
  __stack_top = ORIGIN(RAM) + LENGTH(RAM);   /* stack grows down from RAM top */

  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) }
}

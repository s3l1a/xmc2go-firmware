/*
 * link_slotA.ld - application image for slot A.
 *
 * The raw app binary is linked at slot start + 0x20: the 32-byte image header
 * (common/image.h) is prepended by the host image builder, and the XMC1100
 * user vector table ([SP][reset][0][0][CLK_VAL1][CLK_VAL2]) sits at the start
 * of the raw binary. The bootloader reads SP/reset from slot+0x20/+0x24.
 */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x10003020, LENGTH = 8K - 0x20
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

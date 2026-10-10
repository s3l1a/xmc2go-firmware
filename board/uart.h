#ifndef XMC_UART_H
#define XMC_UART_H

#include <stdint.h>
#include <stddef.h>

/* USIC0_CH0 in ASC mode: TX = P2.1 (DOUT0, ALT6), RX = P2.2 (DX3A->DX0G).
 * 115200 8N1, polled I/O (no interrupts). */
void uart_init(void);
void uart_putc(char c);
void uart_write(const uint8_t *data, size_t len);
void uart_puts(const char *s);
/* Returns 0..255 or -1 if no byte within timeout_ms (0 = non-blocking). */
int uart_getc_timeout(uint32_t timeout_ms);
int uart_getc_nonblock(void);   /* -1 if no data */
void uart_flush_tx(void);

#endif

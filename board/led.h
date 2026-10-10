#ifndef XMC_LED_H
#define XMC_LED_H

#include <stdint.h>

/* LED pin mapping is in common/config.h (schematic: LED1=P1.0, LED2=P1.1). */
void led_init(void);
void led_set(int led, int on);   /* led: 1 or 2 */
void led_toggle(int led);
void led_pattern(uint8_t led1, uint8_t led2);

#endif

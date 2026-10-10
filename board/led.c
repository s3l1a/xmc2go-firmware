#include "xmc1100_regs.h"
#include "led.h"
#include "config.h"

static PORT_Type *led_port(uint32_t port)
{
    switch (port) {
    case 0u:  return PORT0;
    case 1u:  return PORT1;
    default:  return PORT2;
    }
}

static void led_pin_mode(uint32_t port, uint32_t pin)
{
    PORT_Type *p = led_port(port);
    volatile uint32_t *iocr = &p->IOCR0 + (pin / 4u);
    uint32_t shift = 3u + 8u * (pin % 4u);
    *iocr = (*iocr & ~(0x1Fu << shift)) |
            ((uint32_t)PORT_PC_OUT_GPIO_PP << shift);
}

void led_init(void)
{
    led_pin_mode(CFG_LED1_PORT, CFG_LED1_PIN);
    led_pin_mode(CFG_LED2_PORT, CFG_LED2_PIN);
    led_set(1, 0);
    led_set(2, 0);
}

void led_set(int led, int on)
{
    uint32_t port = (led == 1) ? CFG_LED1_PORT : CFG_LED2_PORT;
    uint32_t pin = (led == 1) ? CFG_LED1_PIN : CFG_LED2_PIN;
    PORT_Type *p = led_port(port);
    /* LEDs are active high on XMC 2Go (schematic: pin -> R -> LED -> GND) */
    p->OMR = on ? PORT_OMR_PS(pin) : PORT_OMR_PR(pin);
}

void led_toggle(int led)
{
    uint32_t port = (led == 1) ? CFG_LED1_PORT : CFG_LED2_PORT;
    uint32_t pin = (led == 1) ? CFG_LED1_PIN : CFG_LED2_PIN;
    PORT_Type *p = led_port(port);
    p->OMR = ((p->OUT >> pin) & 1u) ? PORT_OMR_PR(pin) : PORT_OMR_PS(pin);
}

void led_pattern(uint8_t led1, uint8_t led2)
{
    led_set(1, led1 ? 1 : 0);
    led_set(2, led2 ? 1 : 0);
}

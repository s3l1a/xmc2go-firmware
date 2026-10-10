#ifndef XMC_APP_API_H
#define XMC_APP_API_H

#include <stdint.h>

/*
 * Shared application API (linked into every app image).
 *
 * Watchdog contract (see docs/DESIGN.md):
 *  - The bootloader arms the 5 s watchdog and jumps to the app.
 *  - The app MUST call app_service_watchdog() regularly from its main loop,
 *    otherwise the watchdog resets the device and the bootloader rolls back
 *    after CFG_WDT_TRIAL_ATTEMPTS failed trials.
 *  - An app that has passed its self-check calls app_mark_healthy() within the
 *    trial window (before the watchdog fires). That clears the trial flag in
 *    flash metadata and services the watchdog. Healthy apps keep calling
 *    app_service_watchdog() forever after.
 */
void app_service_watchdog(void);

/* Clear the trial flag for the active slot in flash metadata and service the
 * watchdog. Returns 0 on success, -1 if metadata could not be written. */
int app_mark_healthy(void);

/* Milliseconds since boot (CCU40 tick). */
uint32_t app_millis(void);

#endif

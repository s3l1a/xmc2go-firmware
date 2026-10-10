#include "app_api.h"
#include "meta.h"
#include "wdt.h"
#include "timer.h"
#include "config.h"

void app_service_watchdog(void)
{
    wdt_service();
}

int app_mark_healthy(void)
{
    meta_record_t rec;
    uint8_t flags;

    if (!meta_log_read(&rec)) {
        return -1;
    }
    flags = meta_flags_of(&rec, rec.active_slot);
    flags = (uint8_t)((flags | META_FLAG_VALID) & ~(uint8_t)META_FLAG_TRIAL);
    meta_set_flags(&rec, rec.active_slot, flags);
    rec.attempts = 0u;
    rec.seq += 1u;

    if (meta_log_append(&rec) != 0) {
        return -1;
    }
    wdt_service();
    return 0;
}

uint32_t app_millis(void)
{
    return timer_millis();
}

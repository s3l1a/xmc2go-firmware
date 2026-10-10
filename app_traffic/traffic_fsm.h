/*
 * traffic_fsm.h - pure-C traffic light finite state machine. No hardware or
 * OS dependencies so tests/host_fsm can compile it with a host C compiler.
 *
 * States (per specification):
 *   NORMAL_GREEN, NORMAL_YELLOW, NORMAL_RED, PEDESTRIAN_REQUEST, FAULT
 * PEDESTRIAN_REQUEST is the pedestrian walk phase: it is entered at the next
 * safe point after a pedestrian button press ('P' sets a pending flag; the
 * cycle finishes GREEN -> YELLOW -> RED and then serves the request).
 *
 * LED mapping (XMC 2Go has only 2 user LEDs, see common/config.h):
 *   LED1 = GREEN aspect, LED2 = RED aspect, YELLOW = both on.
 *   PEDESTRIAN_REQUEST: LED2 on (vehicles stop), LED1 blinks (walk).
 *   FAULT: both LEDs blink fast.
 */
#ifndef TRAFFIC_FSM_H
#define TRAFFIC_FSM_H

#include <stdint.h>

typedef enum {
    TRAFFIC_STATE_NORMAL_GREEN = 0,
    TRAFFIC_STATE_NORMAL_YELLOW = 1,
    TRAFFIC_STATE_NORMAL_RED = 2,
    TRAFFIC_STATE_PEDESTRIAN_REQUEST = 3,
    TRAFFIC_STATE_FAULT = 4
} traffic_state_t;

typedef enum {
    TRAFFIC_EVT_TICK = 0,        /* 1 ms elapsed */
    TRAFFIC_EVT_PED_BUTTON = 1,  /* 'P' */
    TRAFFIC_EVT_RESET_CYCLE = 2, /* 'R' */
    TRAFFIC_EVT_STATUS_REQ = 3,  /* 'S' */
    TRAFFIC_EVT_INVALID = 0xFF   /* deliberately invalid event */
} traffic_event_t;

typedef enum {
    TRAFFIC_TRANS_NONE = 0,
    TRAFFIC_TRANS_TIMEOUT = 1,       /* timed state change */
    TRAFFIC_TRANS_PED_PENDING = 2,   /* request queued */
    TRAFFIC_TRANS_PED_SERVED = 3,    /* walk phase finished */
    TRAFFIC_TRANS_RESET = 4,         /* cycle reset */
    TRAFFIC_TRANS_TO_FAULT = 5,      /* invalid event */
    TRAFFIC_TRANS_FAULT_HOLD = 6,    /* event ignored in FAULT */
    TRAFFIC_TRANS_STATUS = 7         /* status request handled */
} traffic_transition_t;

/* Timing table (all times in ms). */
typedef struct {
    uint32_t green_ms;
    uint32_t yellow_ms;
    uint32_t red_ms;
    uint32_t ped_walk_ms;
    uint32_t walk_blink_ms;
    uint32_t fault_blink_ms;
} traffic_timing_t;

extern const traffic_timing_t TRAFFIC_TIMING;

typedef struct {
    traffic_state_t state;
    uint32_t time_in_state_ms;
    uint8_t ped_pending;
    uint8_t led1;
    uint8_t led2;
} traffic_fsm_t;

typedef struct {
    traffic_state_t state;
    uint32_t time_in_state_ms;
    uint32_t time_remaining_ms;  /* 0 in FAULT (no timed exit) */
    uint8_t ped_pending;
    uint8_t led1;
    uint8_t led2;
} traffic_status_t;

void traffic_fsm_init(traffic_fsm_t *fsm);

/* Advance the FSM by one event. Returns the transition that resulted
 * (TRAFFIC_TRANS_NONE for pure timer ticks without a state change). */
traffic_transition_t traffic_fsm_step(traffic_fsm_t *fsm, traffic_event_t evt);

/* Duration of the current state from the timing table (0 = no timed exit). */
uint32_t traffic_state_duration(traffic_state_t state);

/* Human readable state name (constant string). */
const char *traffic_state_name(traffic_state_t state);

void traffic_fsm_get_status(const traffic_fsm_t *fsm, traffic_status_t *out);

#endif /* TRAFFIC_FSM_H */

#include "traffic_fsm.h"

const traffic_timing_t TRAFFIC_TIMING = {
    5000u,  /* green_ms */
    2000u,  /* yellow_ms */
    5000u,  /* red_ms */
    4000u,  /* ped_walk_ms (PEDESTRIAN_REQUEST duration) */
    250u,   /* walk_blink_ms */
    125u    /* fault_blink_ms */
};

uint32_t traffic_state_duration(traffic_state_t state)
{
    switch (state) {
    case TRAFFIC_STATE_NORMAL_GREEN:
        return TRAFFIC_TIMING.green_ms;
    case TRAFFIC_STATE_NORMAL_YELLOW:
        return TRAFFIC_TIMING.yellow_ms;
    case TRAFFIC_STATE_NORMAL_RED:
        return TRAFFIC_TIMING.red_ms;
    case TRAFFIC_STATE_PEDESTRIAN_REQUEST:
        return TRAFFIC_TIMING.ped_walk_ms;
    case TRAFFIC_STATE_FAULT:
    default:
        return 0u; /* no timed exit */
    }
}

const char *traffic_state_name(traffic_state_t state)
{
    switch (state) {
    case TRAFFIC_STATE_NORMAL_GREEN:   return "NORMAL_GREEN";
    case TRAFFIC_STATE_NORMAL_YELLOW:  return "NORMAL_YELLOW";
    case TRAFFIC_STATE_NORMAL_RED:     return "NORMAL_RED";
    case TRAFFIC_STATE_PEDESTRIAN_REQUEST: return "PEDESTRIAN_REQUEST";
    case TRAFFIC_STATE_FAULT:          return "FAULT";
    default:                           return "?";
    }
}

static void fsm_update_outputs(traffic_fsm_t *fsm)
{
    switch (fsm->state) {
    case TRAFFIC_STATE_NORMAL_GREEN:
        fsm->led1 = 1u; fsm->led2 = 0u;               /* green */
        break;
    case TRAFFIC_STATE_NORMAL_YELLOW:
        fsm->led1 = 1u; fsm->led2 = 1u;               /* yellow = both */
        break;
    case TRAFFIC_STATE_NORMAL_RED:
        fsm->led1 = 0u; fsm->led2 = 1u;               /* red */
        break;
    case TRAFFIC_STATE_PEDESTRIAN_REQUEST:
        fsm->led2 = 1u;                                /* vehicles stop */
        fsm->led1 = (uint8_t)((fsm->time_in_state_ms / TRAFFIC_TIMING.walk_blink_ms) & 1u);
        break;
    case TRAFFIC_STATE_FAULT:
    default:
        fsm->led1 = (uint8_t)((fsm->time_in_state_ms / TRAFFIC_TIMING.fault_blink_ms) & 1u);
        fsm->led2 = fsm->led1;
        break;
    }
}

static void fsm_enter(traffic_fsm_t *fsm, traffic_state_t state)
{
    fsm->state = state;
    fsm->time_in_state_ms = 0u;
    fsm_update_outputs(fsm);
}

void traffic_fsm_init(traffic_fsm_t *fsm)
{
    fsm->ped_pending = 0u;
    fsm_enter(fsm, TRAFFIC_STATE_NORMAL_GREEN);
}

static traffic_transition_t fsm_on_timeout(traffic_fsm_t *fsm)
{
    switch (fsm->state) {
    case TRAFFIC_STATE_NORMAL_GREEN:
        fsm_enter(fsm, TRAFFIC_STATE_NORMAL_YELLOW);
        return TRAFFIC_TRANS_TIMEOUT;
    case TRAFFIC_STATE_NORMAL_YELLOW:
        fsm_enter(fsm, TRAFFIC_STATE_NORMAL_RED);
        return TRAFFIC_TRANS_TIMEOUT;
    case TRAFFIC_STATE_NORMAL_RED:
        if (fsm->ped_pending) {
            fsm->ped_pending = 0u; /* request consumed by starting the walk */
            fsm_enter(fsm, TRAFFIC_STATE_PEDESTRIAN_REQUEST);
        } else {
            fsm_enter(fsm, TRAFFIC_STATE_NORMAL_GREEN);
        }
        return TRAFFIC_TRANS_TIMEOUT;
    case TRAFFIC_STATE_PEDESTRIAN_REQUEST:
        fsm_enter(fsm, TRAFFIC_STATE_NORMAL_GREEN);
        return TRAFFIC_TRANS_PED_SERVED;
    case TRAFFIC_STATE_FAULT:
    default:
        return TRAFFIC_TRANS_NONE;
    }
}

traffic_transition_t traffic_fsm_step(traffic_fsm_t *fsm, traffic_event_t evt)
{
    traffic_transition_t trans = TRAFFIC_TRANS_NONE;

    switch (evt) {
    case TRAFFIC_EVT_TICK:
        fsm->time_in_state_ms++;
        fsm_update_outputs(fsm);
        if (traffic_state_duration(fsm->state) != 0u &&
            fsm->time_in_state_ms >= traffic_state_duration(fsm->state)) {
            trans = fsm_on_timeout(fsm);
        }
        break;

    case TRAFFIC_EVT_PED_BUTTON:
        if (fsm->state == TRAFFIC_STATE_FAULT) {
            trans = TRAFFIC_TRANS_FAULT_HOLD;
        } else {
            fsm->ped_pending = 1u;
            trans = TRAFFIC_TRANS_PED_PENDING;
        }
        break;

    case TRAFFIC_EVT_RESET_CYCLE:
        fsm->ped_pending = 0u;
        fsm_enter(fsm, TRAFFIC_STATE_NORMAL_GREEN);
        trans = TRAFFIC_TRANS_RESET;
        break;

    case TRAFFIC_EVT_STATUS_REQ:
        trans = TRAFFIC_TRANS_STATUS;
        break;

    case TRAFFIC_EVT_INVALID:
    default:
        if (fsm->state == TRAFFIC_STATE_FAULT) {
            trans = TRAFFIC_TRANS_FAULT_HOLD;
        } else {
            fsm->ped_pending = 0u;
            fsm_enter(fsm, TRAFFIC_STATE_FAULT);
            trans = TRAFFIC_TRANS_TO_FAULT;
        }
        break;
    }
    return trans;
}

void traffic_fsm_get_status(const traffic_fsm_t *fsm, traffic_status_t *out)
{
    uint32_t dur = traffic_state_duration(fsm->state);
    out->state = fsm->state;
    out->time_in_state_ms = fsm->time_in_state_ms;
    out->time_remaining_ms =
        (dur == 0u || fsm->time_in_state_ms >= dur)
            ? 0u : (dur - fsm->time_in_state_ms);
    out->ped_pending = fsm->ped_pending;
    out->led1 = fsm->led1;
    out->led2 = fsm->led2;
}

/*
 * fsm_test.c - host tests for the traffic light FSM (compiled with gcc or MSVC).
 * Fake clock: time only advances via TRAFFIC_EVT_TICK events.
 */
#include <stdio.h>
#include <string.h>
#include "traffic_fsm.h"

static int failures = 0;
static int checks = 0;

static void check_int(const char *name, long got, long want)
{
    checks++;
    if (got != want) {
        printf("FAIL %s: got %ld want %ld\n", name, got, want);
        failures++;
    }
}

static void check_str(const char *name, const char *got, const char *want)
{
    checks++;
    if (strcmp(got, want) != 0) {
        printf("FAIL %s: got '%s' want '%s'\n", name, got, want);
        failures++;
    }
}

static void tick_n(traffic_fsm_t *fsm, uint32_t n)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        traffic_fsm_step(fsm, TRAFFIC_EVT_TICK);
    }
}

static void test_config_table(void)
{
    check_int("green_ms", (long)TRAFFIC_TIMING.green_ms, 5000);
    check_int("yellow_ms", (long)TRAFFIC_TIMING.yellow_ms, 2000);
    check_int("red_ms", (long)TRAFFIC_TIMING.red_ms, 5000);
    check_int("ped_walk_ms", (long)TRAFFIC_TIMING.ped_walk_ms, 4000);
    check_int("state_duration(GREEN)", (long)traffic_state_duration(TRAFFIC_STATE_NORMAL_GREEN), 5000);
    check_int("state_duration(FAULT)", (long)traffic_state_duration(TRAFFIC_STATE_FAULT), 0);
}

static void test_state_names(void)
{
    check_str("name(GREEN)", traffic_state_name(TRAFFIC_STATE_NORMAL_GREEN), "NORMAL_GREEN");
    check_str("name(YELLOW)", traffic_state_name(TRAFFIC_STATE_NORMAL_YELLOW), "NORMAL_YELLOW");
    check_str("name(RED)", traffic_state_name(TRAFFIC_STATE_NORMAL_RED), "NORMAL_RED");
    check_str("name(PED)", traffic_state_name(TRAFFIC_STATE_PEDESTRIAN_REQUEST), "PEDESTRIAN_REQUEST");
    check_str("name(FAULT)", traffic_state_name(TRAFFIC_STATE_FAULT), "FAULT");
}

static void test_init(void)
{
    traffic_fsm_t fsm;
    traffic_status_t st;
    traffic_fsm_init(&fsm);
    traffic_fsm_get_status(&fsm, &st);
    check_int("init.state", (long)st.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    check_int("init.time", (long)st.time_in_state_ms, 0);
    check_int("init.led1", (long)st.led1, 1);
    check_int("init.led2", (long)st.led2, 0);
    check_int("init.ped_pending", (long)st.ped_pending, 0);
    check_int("init.remaining", (long)st.time_remaining_ms, 5000);
}

static void test_normal_cycle_transitions(void)
{
    traffic_fsm_t fsm;
    traffic_transition_t t;

    traffic_fsm_init(&fsm);

    /* GREEN for exactly green_ms-1 ticks: no transition yet */
    tick_n(&fsm, 4999);
    check_int("green_stable.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    /* tick 5000 -> YELLOW */
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_TICK);
    check_int("green->yellow.trans", (long)t, (long)TRAFFIC_TRANS_TIMEOUT);
    check_int("green->yellow.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_YELLOW);

    tick_n(&fsm, 1999);
    check_int("yellow_stable.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_YELLOW);
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_TICK);
    check_int("yellow->red.trans", (long)t, (long)TRAFFIC_TRANS_TIMEOUT);
    check_int("yellow->red.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_RED);

    tick_n(&fsm, 4999);
    check_int("red_stable.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_RED);
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_TICK);
    check_int("red->green.trans", (long)t, (long)TRAFFIC_TRANS_TIMEOUT);
    check_int("red->green.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    check_int("red->green.led1", (long)fsm.led1, 1);
    check_int("red->green.led2", (long)fsm.led2, 0);
}

static void test_pedestrian_request_timing(void)
{
    traffic_fsm_t fsm;
    traffic_status_t st;
    traffic_transition_t t;

    traffic_fsm_init(&fsm);
    tick_n(&fsm, 1000);                       /* in GREEN */

    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    check_int("ped.press.trans", (long)t, (long)TRAFFIC_TRANS_PED_PENDING);
    check_int("ped.press.pending", (long)fsm.ped_pending, 1);
    check_int("ped.press.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);

    /* finish GREEN -> YELLOW -> RED */
    tick_n(&fsm, 4000);                       /* GREEN ends at 5000 */
    check_int("ped.to_yellow", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_YELLOW);
    tick_n(&fsm, 2000);
    check_int("ped.to_red", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_RED);
    tick_n(&fsm, 5000);
    /* safe point: RED finished -> walk phase */
    check_int("ped.to_walk", (long)fsm.state, (long)TRAFFIC_STATE_PEDESTRIAN_REQUEST);
    check_int("ped.walk.led2", (long)fsm.led2, 1);

    /* walk phase lasts ped_walk_ms then back to GREEN */
    tick_n(&fsm, 3999);
    check_int("ped.walk.hold", (long)fsm.state, (long)TRAFFIC_STATE_PEDESTRIAN_REQUEST);
    tick_n(&fsm, 1);
    traffic_fsm_get_status(&fsm, &st);
    check_int("ped.walk.done.state", (long)st.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    check_int("ped.walk.done.pending", (long)st.ped_pending, 0);
}

static void test_ped_request_during_walk(void)
{
    traffic_fsm_t fsm;
    traffic_fsm_init(&fsm);
    traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    tick_n(&fsm, 5000 + 2000 + 5000);        /* reach walk phase */
    check_int("walk.state", (long)fsm.state, (long)TRAFFIC_STATE_PEDESTRIAN_REQUEST);
    check_int("walk.pending_consumed", (long)fsm.ped_pending, 0);
    /* pressing again during walk queues a new request for the next cycle */
    traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    check_int("walk.repress.pending", (long)fsm.ped_pending, 1);
    tick_n(&fsm, 4000);                       /* walk ends -> GREEN */
    check_int("walk.end.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    check_int("walk.end.pending", (long)fsm.ped_pending, 1);
    /* next full cycle serves it */
    tick_n(&fsm, 5000 + 2000 + 5000);
    check_int("second_walk.state", (long)fsm.state, (long)TRAFFIC_STATE_PEDESTRIAN_REQUEST);
}

static void test_led_outputs(void)
{
    traffic_fsm_t fsm;
    traffic_fsm_init(&fsm);
    check_int("led.green.l1", (long)fsm.led1, 1);
    check_int("led.green.l2", (long)fsm.led2, 0);
    tick_n(&fsm, 5000);
    check_int("led.yellow.l1", (long)fsm.led1, 1);
    check_int("led.yellow.l2", (long)fsm.led2, 1);
    tick_n(&fsm, 2000);
    check_int("led.red.l1", (long)fsm.led1, 0);
    check_int("led.red.l2", (long)fsm.led2, 1);
    /* walk blink: first half blink period led1=0, second =1 */
    traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    tick_n(&fsm, 5000);
    check_int("walk.at0.l1", (long)fsm.led1, 0);
    tick_n(&fsm, 250);
    check_int("walk.at250.l1", (long)fsm.led1, 1);
    tick_n(&fsm, 250);
    check_int("walk.at500.l1", (long)fsm.led1, 0);
}

static void test_reset(void)
{
    traffic_fsm_t fsm;
    traffic_transition_t t;

    traffic_fsm_init(&fsm);
    tick_n(&fsm, 3000);
    traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_RESET_CYCLE);
    check_int("reset.trans", (long)t, (long)TRAFFIC_TRANS_RESET);
    check_int("reset.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    check_int("reset.time", (long)fsm.time_in_state_ms, 0);
    check_int("reset.pending", (long)fsm.ped_pending, 0);

    /* reset also works from FAULT */
    traffic_fsm_step(&fsm, TRAFFIC_EVT_INVALID);
    check_int("reset.from_fault.pre", (long)fsm.state, (long)TRAFFIC_STATE_FAULT);
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_RESET_CYCLE);
    check_int("reset.from_fault.trans", (long)t, (long)TRAFFIC_TRANS_RESET);
    check_int("reset.from_fault.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
}

static void test_invalid_input_and_fault(void)
{
    traffic_fsm_t fsm;
    traffic_status_t st;
    traffic_transition_t t;
    uint32_t i;

    traffic_fsm_init(&fsm);
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_INVALID);
    check_int("invalid.trans", (long)t, (long)TRAFFIC_TRANS_TO_FAULT);
    check_int("invalid.state", (long)fsm.state, (long)TRAFFIC_STATE_FAULT);
    check_int("invalid.pending_cleared", (long)fsm.ped_pending, 0);

    /* FAULT is stable under ticks (no timed exit) */
    tick_n(&fsm, 100000);
    check_int("fault.stable", (long)fsm.state, (long)TRAFFIC_STATE_FAULT);
    traffic_fsm_get_status(&fsm, &st);
    check_int("fault.remaining", (long)st.time_remaining_ms, 0);
    check_int("fault.time_counts", (long)st.time_in_state_ms, 100000);

    /* FAULT blinks both LEDs */
    i = fsm.time_in_state_ms / TRAFFIC_TIMING.fault_blink_ms;
    check_int("fault.blink.l1", (long)fsm.led1, (long)(i & 1u));
    check_int("fault.blink.l2", (long)fsm.led2, (long)(i & 1u));

    /* invalid event in FAULT is ignored */
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_INVALID);
    check_int("fault.invalid.hold", (long)t, (long)TRAFFIC_TRANS_FAULT_HOLD);
    /* ped button in FAULT is ignored */
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    check_int("fault.ped.hold", (long)t, (long)TRAFFIC_TRANS_FAULT_HOLD);
    check_int("fault.state2", (long)fsm.state, (long)TRAFFIC_STATE_FAULT);
}

static void test_status_event(void)
{
    traffic_fsm_t fsm;
    traffic_status_t st;
    traffic_transition_t t;

    traffic_fsm_init(&fsm);
    tick_n(&fsm, 1000);
    t = traffic_fsm_step(&fsm, TRAFFIC_EVT_STATUS_REQ);
    check_int("status.trans", (long)t, (long)TRAFFIC_TRANS_STATUS);
    check_int("status.state", (long)fsm.state, (long)TRAFFIC_STATE_NORMAL_GREEN);
    check_int("status.time", (long)fsm.time_in_state_ms, 1000);
    traffic_fsm_get_status(&fsm, &st);
    check_int("status.remaining", (long)st.time_remaining_ms, 4000);
}

static void test_status_remaining_across_states(void)
{
    traffic_fsm_t fsm;
    traffic_status_t st;
    traffic_fsm_init(&fsm);
    tick_n(&fsm, 5000);
    traffic_fsm_get_status(&fsm, &st);
    check_int("remaining.yellow", (long)st.time_remaining_ms, 2000);
    tick_n(&fsm, 2000);
    traffic_fsm_get_status(&fsm, &st);
    check_int("remaining.red", (long)st.time_remaining_ms, 5000);
    tick_n(&fsm, 1234);
    traffic_fsm_get_status(&fsm, &st);
    check_int("remaining.red2", (long)st.time_remaining_ms, 3766);
}

static void test_ped_in_yellow_and_red(void)
{
    traffic_fsm_t fsm;
    traffic_fsm_init(&fsm);
    tick_n(&fsm, 5000);                        /* YELLOW */
    traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    check_int("ped_yellow.pending", (long)fsm.ped_pending, 1);
    tick_n(&fsm, 2000);                        /* RED */
    tick_n(&fsm, 5000);                        /* RED done */
    check_int("ped_yellow.served", (long)fsm.state, (long)TRAFFIC_STATE_PEDESTRIAN_REQUEST);

    traffic_fsm_init(&fsm);
    tick_n(&fsm, 5000 + 2000);                 /* RED */
    traffic_fsm_step(&fsm, TRAFFIC_EVT_PED_BUTTON);
    tick_n(&fsm, 5000);
    check_int("ped_red.served", (long)fsm.state, (long)TRAFFIC_STATE_PEDESTRIAN_REQUEST);
}

int main(void)
{
    test_config_table();
    test_state_names();
    test_init();
    test_normal_cycle_transitions();
    test_pedestrian_request_timing();
    test_ped_request_during_walk();
    test_led_outputs();
    test_reset();
    test_invalid_input_and_fault();
    test_status_event();
    test_status_remaining_across_states();
    test_ped_in_yellow_and_red();

    if (failures == 0) {
        printf("ALL FSM TESTS PASS (%d checks)\n", checks);
        return 0;
    }
    printf("%d/%d FSM CHECKS FAILED\n", failures, checks);
    return 1;
}

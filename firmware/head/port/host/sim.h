/* rr_head_sim: emulated detector head = the real firmware core on Linux + a physics/fault model
 * behind the HAL. See firmware/head/README.md for the socket protocols. */
#ifndef RRH_SIM_H
#define RRH_SIM_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "rrh_core.h"

#define SIM_TICK_HZ 144000000u /* same tick as the capture timers of the target port */
#define SIM_CH 5u             /* alpha, beta, ref, floor_reject, ref_reject */
#define SIM_SCHED_MAX 2048u

typedef struct {
    uint64_t from_us;
    uint32_t mask; /* bit (lane * SIM_CH + ch) set: value present */
    double rate[RRH_LANES][SIM_CH];
} sim_rate_change_t;

typedef struct {
    /* clock */
    bool manual;
    uint64_t manual_us;
    uint64_t boot_mono_ns; /* CLOCK_MONOTONIC at head-clock zero (real mode) */
    uint32_t turnaround_us;
    /* random numbers */
    uint64_t rng[4];
    uint64_t ent[4];
    /* stimulus */
    double rate[RRH_LANES][SIM_CH];
    sim_rate_change_t sched[SIM_SCHED_MAX];
    uint32_t n_sched;
    double tau_floor_us, tau_ref_us;
    /* acquisition source */
    bool running;
    bool stopping;
    uint32_t stop_after; /* last gate index to deliver when stopping */
    uint32_t span_us;
    uint64_t t0_us;
    uint32_t next_gate;
    uint32_t skip_gates; /* injection: drop this many records */
    uint64_t tick_offset;
    uint32_t arm_delay_us;
    bool heater_req, heater_applied, heater_last_gate;
    /* front end / housekeeping model */
    rrh_frontend_cfg_t fe;
    uint32_t bias_set_mv;
    bool bias_enable;
    rrh_analog_t analog;       /* values handed to the core (injectable) */
    bool sipm_open[RRH_LANES];
    double plate_heat_c;
    double ambient_c;
    bool plate_open;
    uint64_t model_us;
    uint8_t saturate_mask;     /* bit n floor lane n, bit 4+n reference lane n */
    bool source_fail;          /* acquisition source refuses to start */
    bool width_hist;           /* fabricate the optional pulse-width histogram */
    /* board functions of IB-17 (modelled, not measured): anode current monitor, expander, bias permit */
    double imon_ua[RRH_CHAINS]; /* SiPM anode current per chain while the bias is on (default 1.0 uA, J60035 dark class) */
    uint8_t imon_valid;         /* chains the monitor scan reports as converted */
    int32_t imon_offset_uv;     /* offset error added to every IMON reading */
    bool exp_present;           /* TCA9534 answers */
    bool inhibit;               /* inhibit bus asserted by something other than the lid (OVP, +5V_A low) */
    bool lid_open;
    bool efuse_fault;
    bool permit;                /* modelled permit latch: set by HV_EN rising edge with no inhibit, cleared by any inhibit */
    bool bias_enable_prev;
    uint8_t hw_rev;
    /* storage */
    uint8_t nv[256];
    size_t nv_len;
    /* waveform */
    rrh_wave_cfg_t wave;
    rrh_wave_state_t wave_state;
    /* bookkeeping */
    rrh_reset_cause_t reset_cause;
    uint32_t boot_count;
    uint64_t gates_total;
    uint64_t drawn[RRH_LANES][SIM_CH];
    FILE *truth;
    bool have_forced_boot_id;
    uint8_t forced_boot_id[16];
} sim_t;

extern sim_t g_sim;

void sim_init(sim_t *s, uint64_t seed, bool manual);
void sim_power_cycle(sim_t *s); /* state lost at an MCU reset (clock, acquisition, heater) */
uint64_t sim_mono_ns(void);
bool sim_add_rate_change(sim_t *s, const sim_rate_change_t *chg);

#endif

/* HAL of the head core on RR-HEAD-ACQ (STM32G474VET6). Glue only. NOT TESTED ON HARDWARE.
 * Analog scale factors are the design values noted in pinmap.yaml and must be replaced by the
 * as-built values of the board (head electronics lead). */
#include <string.h>

#include "bsp.h"
#include "rr_common.h"

static bool g_dac_ok;

uint64_t rrh_hal_now_us(void) { return bsp_now_us(); }

uint64_t rrh_hal_reply_tx_time_us(uint64_t rx_us)
{
    /* A TIME reply starts BSP_TIME_REPLY_DELAY_US after the end of the request, or as soon as
     * possible if the main loop was late; the service interrupt releases it within 10 us. */
    const uint64_t now = bsp_now_us();
    const uint64_t planned = rx_us + BSP_TIME_REPLY_DELAY_US;
    return (planned > (now + 300u)) ? planned : (now + 300u);
}

bool rrh_hal_entropy(uint8_t *buf, size_t len)
{
    /* TRNG words conditioned with the device UID and the clock through SHA-256, so the result is
     * device- and boot-specific even if the TRNG reports an error (then false is returned). */
    struct {
        uint32_t rnd[8];
        uint8_t uid[12];
        uint64_t ticks;
        uint32_t adc[4];
    } pool;
    uint8_t digest[RRC_SHA256_LEN];
    memset(&pool, 0, sizeof pool);
    const bool ok = bsp_rng_words(pool.rnd, 8u);
    bsp_uid(pool.uid);
    pool.ticks = bsp_now_ticks();
    for (uint32_t i = 0u; i < 4u; i++) {
        pool.adc[i] = bsp_adc_code((bsp_adc_ch_t)(BSP_ADC_NTC0 + i));
    }
    rrc_sha256(&pool, sizeof pool, digest);
    memcpy(buf, digest, (len < sizeof digest) ? len : sizeof digest);
    return ok;
}

rrh_reset_cause_t rrh_hal_reset_cause(void) { return bsp_reset_cause(); }
void rrh_hal_watchdog_kick(void) { bsp_watchdog_kick(); }

bool rrh_hal_acq_start(uint32_t span_us, rrh_epoch_t *epoch) { return evt_port_start(span_us, epoch); }
bool rrh_hal_acq_stop(void) { return evt_port_stop(); }
void rrh_hal_acq_abort(void) { evt_port_abort(); }
bool rrh_hal_acq_running(void) { return evt_port_running(); }
bool rrh_hal_acq_poll(rrh_gate_record_t *rec) { return evt_port_poll(rec); }

/* DAC allocation of pinmap.yaml `dac_map`. */
bool rrh_hal_frontend_apply(const rrh_frontend_cfg_t *cfg)
{
    if (!g_dac_ok) {
        g_dac_ok = bsp_dac_init();
    }
    for (uint8_t lane = 0u; lane < RRH_LANES; lane++) {
        const uint8_t dev = (uint8_t)(lane / 2u);
        const uint8_t base = (uint8_t)((lane % 2u) * 3u);
        bsp_dac_write(dev, base, cfg->threshold[(lane * 3u)]);               /* BETA_LLD */
        bsp_dac_write(dev, (uint8_t)(base + 1u), cfg->threshold[(lane * 3u) + 1u]); /* BETA_ULD */
        bsp_dac_write(dev, (uint8_t)(base + 2u), cfg->threshold[(lane * 3u) + 2u]); /* ALPHA */
        bsp_dac_write(2u, (uint8_t)(lane * 2u), cfg->threshold[12u + (lane * 2u)]);            /* REF_LLD */
        bsp_dac_write(2u, (uint8_t)((lane * 2u) + 1u), cfg->threshold[12u + (lane * 2u) + 1u]); /* REF_ULD */
    }
    for (uint8_t i = 0u; i < RRH_N_TRIMS; i++) {
        bsp_dac_write(3u, i, cfg->trim[i]);
    }
    bsp_dac_write(1u, 6u, cfg->pulser_code);
    bsp_pulser(cfg->pulser_enable);
    evt_port_chain_enable(cfg->chain_enable);
    return g_dac_ok;
}

void rrh_hal_bias_set(uint32_t millivolts, bool enable)
{
    /* HV_SET: 0..60 V for DAC code 0..4095 (placeholder transfer function of the bias converter). */
    const uint32_t code = (millivolts >= 60000u) ? 4095u : ((millivolts * 4095u) / 60000u);
    bsp_dac_write(0u, 6u, (uint16_t)code);
    bsp_gpio_write(PIN_HV_EN_PORT, PIN_HV_EN_PIN, enable);
}

void rrh_hal_analog_read(rrh_analog_t *out)
{
    const bool valid = bsp_adc_valid();
    memset(out, 0, sizeof *out);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        int32_t t = valid ? bsp_ntc_mc(bsp_adc_code((bsp_adc_ch_t)(BSP_ADC_NTC0 + lane))) : RRH_TEMP_INVALID;
        if (t == RRH_TEMP_INVALID) {
            t = bsp_tmp117_mc((uint8_t)(lane / 2u)); /* fall back to the TMP117 of that half of the head */
        }
        out->sipm_mc[lane] = t;
    }
    out->heater_plate_mc = valid ? bsp_ntc_mc(bsp_adc_code(BSP_ADC_NTC_HTR)) : RRH_TEMP_INVALID;
    out->board_mc = valid ? bsp_ntc_mc(bsp_adc_code(BSP_ADC_NTC_BOARD)) : RRH_TEMP_INVALID;
    out->bias_mv = bsp_adc_mv(BSP_ADC_BIAS_V) * 25u; /* divider 1:25 */
    out->bias_ua = bsp_adc_mv(BSP_ADC_BIAS_I) / 10u; /* 2.5 V = 250 uA */
    out->bias_valid = valid;
    out->supply_mv = (bsp_adc_mv(BSP_ADC_VIN) * 66u) / 10u; /* divider 1:6.6 */
    out->supply_valid = valid;
    out->heater_cutout_ok = bsp_gpio_read(PIN_HTR_CUTOUT_OK_PORT, PIN_HTR_CUTOUT_OK_PIN);
    out->bumper_zones = (uint8_t)((bsp_gpio_read(PIN_BUMP_ZONE_F_N_PORT, PIN_BUMP_ZONE_F_N_PIN) ? 0u : 1u) |
                                  (bsp_gpio_read(PIN_BUMP_ZONE_L_N_PORT, PIN_BUMP_ZONE_L_N_PIN) ? 0u : 2u) |
                                  (bsp_gpio_read(PIN_BUMP_ZONE_R_N_PORT, PIN_BUMP_ZONE_R_N_PIN) ? 0u : 4u));
    out->frontend_fault = 0u; /* rev A has no per-channel front-end monitor (see README, known gaps) */
}

void rrh_hal_heater_request(bool on) { evt_port_heater_request(on); }

bool rrh_hal_nv_load(uint8_t slot, uint8_t *buf, size_t cap, size_t *len)
{
    return (slot == RRH_NV_SLOT_SETUP) && bsp_nv_load(buf, cap, len);
}

bool rrh_hal_nv_save(uint8_t slot, const uint8_t *buf, size_t len)
{
    return (slot == RRH_NV_SLOT_SETUP) && bsp_nv_save(buf, len);
}

/* Monitor waveform capture is not implemented in this port yet (ADC2 + DMA, stopped by the
 * selected chain's BUSY capture): ENG_WAVE_ARM answers FAULT on the target. */
bool rrh_hal_wave_arm(const rrh_wave_cfg_t *cfg)
{
    (void)cfg;
    return false;
}

rrh_wave_state_t rrh_hal_wave_status(uint16_t *samples, uint32_t *period_ns, uint16_t *trigger_index)
{
    *samples = 0u;
    *period_ns = 0u;
    *trigger_index = 0u;
    return RRH_WAVE_IDLE;
}

bool rrh_hal_wave_read(uint16_t offset, uint16_t count, uint8_t *buf)
{
    (void)offset;
    (void)count;
    (void)buf;
    return false;
}

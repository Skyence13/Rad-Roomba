/* Name tables and persistent configuration (two alternating flash copies, CRC-32, layout version).
 * Values are keyed by the FNV-1a hash of the key name, so adding or removing keys between
 * firmware versions keeps the remaining calibration: unknown hashes are skipped, missing keys
 * keep their default. */
#include <string.h>

#include "rrch.h"

#define X(n) #n,
const char *const rrch_mode_names[RRCH_MODE_N] = {RRCH_MODE_LIST(X)};
const char *const rrch_hw_names[RRCH_HW_N] = {RRCH_HW_LIST(X)};
const char *const rrch_sw_names[RRCH_SW_N] = {RRCH_SW_LIST(X)};
const char *const rrch_opmode_names[RRCH_OP_N] = {RRCH_OPMODE_LIST(X)};
const char *const rrch_pres_names[RRCH_PRES_N] = {RRCH_PRES_LIST(X)};
const char *const rrch_flt_names[RRCH_FLT_N] = {RRCH_FLT_LIST(X)};
const char *const rrch_rref_names[RRCH_RREF_N] = {RRCH_RREF_LIST(X)};
const char *const rrch_tof_names[RRCH_TOF_COUNT] = {RRCH_TOF_LIST(X)};
const char *const rrch_di_names[RRCH_DI_N] = {RRCH_DI_LIST(X)};
const char *const rrch_el_names[RRCH_EL_N] = {RRCH_EL_LIST(X)};
#undef X

#define X(id, name, def, mn, mx, unit) {name, (float)(def), (float)(mn), (float)(mx), unit},
const rrch_cfg_desc_t rrch_cfg_desc[RRCH_CFG_N] = {RRCH_CFG_LIST(X)};
#undef X

#define CFG_MAGIC 0x46435252u /* "RRCF" little endian */

static uint32_t fnv1a(const char *s)
{
    uint32_t h = 2166136261u;
    while (*s) {
        h ^= (uint8_t)*s++;
        h *= 16777619u;
    }
    return h;
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

void rrch_cfg_defaults(rrch_cfg_t *c)
{
    for (int i = 0; i < RRCH_CFG_N; i++) {
        c->v[i] = rrch_cfg_desc[i].def;
    }
    c->gen = 0;
    c->crc = 0;
    c->from_flash = false;
}

int rrch_cfg_find(const char *name)
{
    for (int i = 0; i < RRCH_CFG_N; i++) {
        if (strcmp(name, rrch_cfg_desc[i].name) == 0) {
            return i;
        }
    }
    return -1;
}

/* image: magic, layout version, count, generation, count x (hash, float bits), crc32 of all before */
size_t rrch_cfg_pack(const rrch_cfg_t *c, uint8_t *buf, size_t cap)
{
    size_t need = 16u + 8u * (size_t)RRCH_CFG_N + 4u;
    if (cap < need) {
        return 0;
    }
    put32(buf, CFG_MAGIC);
    put32(buf + 4, RRCH_CFG_LAYOUT_VERSION);
    put32(buf + 8, (uint32_t)RRCH_CFG_N);
    put32(buf + 12, c->gen);
    for (int i = 0; i < RRCH_CFG_N; i++) {
        uint32_t bits;
        memcpy(&bits, &c->v[i], 4);
        put32(buf + 16 + 8 * i, fnv1a(rrch_cfg_desc[i].name));
        put32(buf + 20 + 8 * i, bits);
    }
    put32(buf + need - 4, rrc_crc32(buf, need - 4));
    return need;
}

bool rrch_cfg_unpack(rrch_cfg_t *c, const uint8_t *buf, size_t len)
{
    if (len < 20u || get32(buf) != CFG_MAGIC || get32(buf + 4) != RRCH_CFG_LAYOUT_VERSION) {
        return false;
    }
    uint32_t n = get32(buf + 8);
    if (n > 512u || len != 16u + 8u * n + 4u) {
        return false;
    }
    uint32_t crc = rrc_crc32(buf, len - 4);
    if (get32(buf + len - 4) != crc) {
        return false;
    }
    rrch_cfg_defaults(c);
    for (uint32_t k = 0; k < n; k++) {
        uint32_t h = get32(buf + 16 + 8 * k);
        for (int i = 0; i < RRCH_CFG_N; i++) {
            if (fnv1a(rrch_cfg_desc[i].name) == h) {
                float f;
                uint32_t bits = get32(buf + 20 + 8 * k);
                memcpy(&f, &bits, 4);
                /* a stored value outside the present limits (or NaN) falls back to the default */
                if (f >= rrch_cfg_desc[i].min && f <= rrch_cfg_desc[i].max) {
                    c->v[i] = f;
                }
                break;
            }
        }
    }
    c->gen = get32(buf + 12);
    c->crc = crc;
    c->from_flash = true;
    return true;
}

bool rrch_cfg_load(rrch_cfg_t *c, const rrch_hal_t *hal)
{
    uint8_t buf[RRCH_NV_MAX];
    rrch_cfg_t best, cand;
    bool have = false;
    for (int slot = RRCH_NV_SLOT_CFG_A; slot <= RRCH_NV_SLOT_CFG_B; slot++) {
        size_t len = 0;
        if (hal->nv_read && hal->nv_read(hal->ctx, slot, buf, sizeof buf, &len) && rrch_cfg_unpack(&cand, buf, len)) {
            if (!have || cand.gen > best.gen) {
                best = cand;
                have = true;
            }
        }
    }
    if (have) {
        *c = best;
    } else {
        rrch_cfg_defaults(c);
        size_t n = rrch_cfg_pack(c, buf, sizeof buf);
        c->crc = rrc_crc32(buf, n - 4);
    }
    return have;
}

bool rrch_cfg_save(rrch_cfg_t *c, const rrch_hal_t *hal)
{
    uint8_t buf[RRCH_NV_MAX];
    uint32_t gen = c->gen + 1u;
    rrch_cfg_t tmp = *c;
    tmp.gen = gen;
    size_t n = rrch_cfg_pack(&tmp, buf, sizeof buf);
    if (n == 0 || !hal->nv_write) {
        return false;
    }
    /* odd generations go to slot A, even to B: the previous good copy is never overwritten */
    int slot = (gen & 1u) ? RRCH_NV_SLOT_CFG_A : RRCH_NV_SLOT_CFG_B;
    if (!hal->nv_write(hal->ctx, slot, buf, n)) {
        return false;
    }
    /* read back and verify before declaring success */
    uint8_t chk[RRCH_NV_MAX];
    size_t len = 0;
    if (!hal->nv_read(hal->ctx, slot, chk, sizeof chk, &len) || len != n || memcmp(chk, buf, n) != 0) {
        return false;
    }
    c->gen = gen;
    c->crc = rrc_crc32(buf, n - 4);
    c->from_flash = true;
    return true;
}

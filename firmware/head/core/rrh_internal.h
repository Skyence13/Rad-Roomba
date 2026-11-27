/* Internal interfaces between the core's translation units. Not for ports. */
#ifndef RRH_INTERNAL_H
#define RRH_INTERNAL_H
#include "rrh_core.h"

/* rrh_setup.c */
bool rrh_setup_valid(const rrh_setup_t *s);
void rrh_setup_compute_id(const rrh_setup_t *s, const char *firmware, char out[24]);
size_t rrh_setup_pack(const rrh_setup_t *s, uint8_t *buf, size_t cap);
bool rrh_setup_unpack(rrh_setup_t *s, const uint8_t *buf, size_t len);
void rrh_setup_to_json(const rrh_setup_t *s, rrc_jw_t *w);
/* Applies the members present in the JSON object `obj` to *s. false = BAD_ARG. */
bool rrh_setup_from_json(rrh_setup_t *s, const rrc_json_t *doc, int obj);
const char *rrh_firmware_id(const rrh_core_t *c);
/* (Re)derive setup_id, descriptor bytes and descriptor SHA-256 from identity + setup. */
bool rrh_descriptor_rebuild(rrh_core_t *c);

/* rrh_acq.c */
void rrh_acq_reset(rrh_core_t *c);                 /* drop frames, sync records, sequence -> 0 */
void rrh_acq_drain(rrh_core_t *c);                 /* take all completed gates from the HAL */
const rrh_frame_t *rrh_acq_oldest(const rrh_core_t *c);
const rrh_frame_t *rrh_acq_newest(const rrh_core_t *c);
const rrh_frame_t *rrh_acq_first_after(const rrh_core_t *c, int64_t after_seq);
const rrh_frame_t *rrh_acq_find(const rrh_core_t *c, uint64_t seq);
void rrh_acq_write_frame(const rrh_core_t *c, const rrh_frame_t *f, rrc_jw_t *w);
void rrh_acq_write_diag(const rrh_core_t *c, const rrh_frame_t *f, rrc_jw_t *w);
/* false = no slot available (every slot is still referenced by retained frames). */
bool rrh_sync_install(rrh_core_t *c, const char *id, uint32_t bound_us, uint64_t expiry_us, uint64_t now_us);
void rrh_sync_pin_newest(rrh_core_t *c);
void rrh_write_health_names(uint16_t health, rrc_jw_t *w);
void rrh_write_zone_names(uint8_t zones, rrc_jw_t *w);

/* rrh_control.c */
void rrh_control_init(rrh_core_t *c);
void rrh_control_sample(rrh_core_t *c);                        /* analog snapshot + health */
void rrh_control_refresh_inputs(rrh_core_t *c);                /* analog, anode monitor, expander: read only */
void rrh_control_periodic(rrh_core_t *c, uint64_t now_us);     /* sample + one bias loop step */
void rrh_control_on_gate(rrh_core_t *c, const rrh_gate_record_t *rec); /* heater decision */
void rrh_control_heater_off(rrh_core_t *c);
uint8_t rrh_control_acq_flags(const rrh_core_t *c);            /* RRH_AF_* for a frame now */
int32_t rrh_control_head_mc(const rrh_core_t *c);
uint16_t rrh_control_clearable(const rrh_core_t *c);           /* latched bits whose cause is gone */

/* rrh_eng.c: additive ops. Returns false if `op` is not one of them. */
bool rrh_eng_dispatch(rrh_core_t *c, const rrc_json_t *doc, const rrc_req_t *req, rrc_jw_t *w);

/* rrh_core.c helpers used by rrh_eng.c */
void rrh_reply_status(rrc_jw_t *w, uint32_t id, const char *status, const char *reason);
void rrh_core_invalidate_binding(rrh_core_t *c);

#endif

/* REQ / RSP envelope shared by the head link (v "2.0") and the chassis link (v "1.0"):
 *
 *   {"type":"REQ","v":<ver>,"id":<u32>,"op":<string>,"args":{...}}
 *   {"type":"RSP","v":<ver>,"id":<u32>,"status":<string>,"body":{...}}
 *
 * plus the last-transaction reply cache that makes a retry with the same id idempotent.
 */
#ifndef RRC_ENVELOPE_H
#define RRC_ENVELOPE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "rrc_json_reader.h"
#include "rrc_json_writer.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    RRC_REQ_OK = 0,
    RRC_REQ_INVALID,     /* not a request this endpoint can answer (no usable id): discard silently */
    RRC_REQ_BAD_VERSION, /* id is usable but "v" differs: answer UNSUPPORTED */
    RRC_REQ_BAD_SHAPE    /* id and version fine, "op" is not a string or "args" is not an object: answer BAD_ARG */
} rrc_req_status_t;

typedef struct {
    uint32_t id;
    int op;   /* token index of the op string (valid for RRC_REQ_OK) */
    int args; /* token index of the args object (valid for RRC_REQ_OK) */
} rrc_req_t;

/* doc must be a successfully parsed document. Unknown top-level members are ignored. */
rrc_req_status_t rrc_req_parse(const rrc_json_t *doc, const char *version, rrc_req_t *out);

/* Writes  {"type":"RSP","v":<ver>,"id":<id>,"status":<status>,"body":  and leaves the writer
 * positioned for the body value (normally an object). */
void rrc_rsp_begin(rrc_jw_t *w, const char *version, uint32_t id, const char *status);
/* Closes the envelope object. */
void rrc_rsp_end(rrc_jw_t *w);
/* Shorthand for a response whose body is {}. */
void rrc_rsp_empty(rrc_jw_t *w, const char *version, uint32_t id, const char *status);

/* Writes a request envelope up to the args value (host side / tests / emulated peers). */
void rrc_req_begin(rrc_jw_t *w, const char *version, uint32_t id, const char *op);
void rrc_req_end(rrc_jw_t *w);

/* Reply cache for the LAST completed transaction. The reply bytes themselves stay in the
 * caller's transmit buffer; this structure only remembers what they answer. A request is a
 * retry when its id AND its exact JSON bytes (length + CRC-32) match the cached request, so
 * a new request that happens to reuse an id is executed, not answered from the cache. */
typedef struct {
    bool valid;
    uint32_t id;
    uint32_t req_crc;
    uint32_t req_len;
    size_t reply_len; /* complete wire length of the cached reply, including the trailer */
} rrc_reply_cache_t;

void rrc_cache_clear(rrc_reply_cache_t *c);
bool rrc_cache_hit(const rrc_reply_cache_t *c, uint32_t id, uint32_t req_crc, size_t req_len);
void rrc_cache_store(rrc_reply_cache_t *c, uint32_t id, uint32_t req_crc, size_t req_len, size_t reply_len);

#ifdef __cplusplus
}
#endif
#endif

#include "rrc_envelope.h"

rrc_req_status_t rrc_req_parse(const rrc_json_t *doc, const char *version, rrc_req_t *out)
{
    if (rrc_json_type(doc, 0) != RRC_JT_OBJECT) {
        return RRC_REQ_INVALID;
    }
    if (!rrc_json_str_eq(doc, rrc_json_get(doc, 0, "type"), "REQ")) {
        return RRC_REQ_INVALID;
    }
    uint64_t id = 0u;
    if (!rrc_json_to_u64(doc, rrc_json_get(doc, 0, "id"), &id) || (id > (uint64_t)UINT32_MAX)) {
        return RRC_REQ_INVALID;
    }
    out->id = (uint32_t)id;
    out->op = -1;
    out->args = -1;
    if (!rrc_json_str_eq(doc, rrc_json_get(doc, 0, "v"), version)) {
        return RRC_REQ_BAD_VERSION;
    }
    const int op = rrc_json_get(doc, 0, "op");
    const int args = rrc_json_get(doc, 0, "args");
    if ((rrc_json_type(doc, op) != RRC_JT_STRING) || (rrc_json_type(doc, args) != RRC_JT_OBJECT)) {
        return RRC_REQ_BAD_SHAPE;
    }
    out->op = op;
    out->args = args;
    return RRC_REQ_OK;
}

void rrc_rsp_begin(rrc_jw_t *w, const char *version, uint32_t id, const char *status)
{
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "type", "RSP");
    rrc_jw_kstr(w, "v", version);
    rrc_jw_ku64(w, "id", id);
    rrc_jw_kstr(w, "status", status);
    rrc_jw_key(w, "body");
}

void rrc_rsp_end(rrc_jw_t *w)
{
    rrc_jw_obj_end(w);
}

void rrc_rsp_empty(rrc_jw_t *w, const char *version, uint32_t id, const char *status)
{
    rrc_rsp_begin(w, version, id, status);
    rrc_jw_obj_begin(w);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

void rrc_req_begin(rrc_jw_t *w, const char *version, uint32_t id, const char *op)
{
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "type", "REQ");
    rrc_jw_kstr(w, "v", version);
    rrc_jw_ku64(w, "id", id);
    rrc_jw_kstr(w, "op", op);
    rrc_jw_key(w, "args");
}

void rrc_req_end(rrc_jw_t *w)
{
    rrc_jw_obj_end(w);
}

void rrc_cache_clear(rrc_reply_cache_t *c)
{
    c->valid = false;
    c->id = 0u;
    c->req_crc = 0u;
    c->req_len = 0u;
    c->reply_len = 0u;
}

bool rrc_cache_hit(const rrc_reply_cache_t *c, uint32_t id, uint32_t req_crc, size_t req_len)
{
    return c->valid && (c->id == id) && (c->req_crc == req_crc) && ((size_t)c->req_len == req_len);
}

void rrc_cache_store(rrc_reply_cache_t *c, uint32_t id, uint32_t req_crc, size_t req_len, size_t reply_len)
{
    c->valid = true;
    c->id = id;
    c->req_crc = req_crc;
    c->req_len = (uint32_t)req_len;
    c->reply_len = reply_len;
}

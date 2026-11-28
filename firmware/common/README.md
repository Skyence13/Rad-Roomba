# firmware/common — portable C11 library shared by the head and chassis firmware

Owner: head firmware lead. Users: `firmware/head` (core, emulator, STM32 port) and
`firmware/chassis`. C11, no dynamic allocation, no OS or libc dependency beyond
`<string.h>`/`<stdint.h>`, no global state: every object lives in caller-supplied storage, so the
same code runs in an interrupt-driven MCU build and in a Linux process.

API stability: version `RR_COMMON_VERSION "0.4.0"` (`include/rr_common.h`). Existing function
signatures will not change within 0.4.x; additions are additive.

## Modules

| Header | What it provides |
|---|---|
| `rrc_crc32.h` | CRC-32 as Python `zlib.crc32` (check value `CBF43926`), one-shot and incremental. |
| `rrc_frame.h` | Record framing of head ICD §4: `JSON TAB 8-uppercase-hex-CRC LF`. `rrc_frame_finish()` appends the trailer; `rrc_frame_rx_push()` is a byte-fed receiver implementing the discard rules (oversize line swallowed through the next LF, wrong TAB count, CR, lowercase or short CRC field, CRC mismatch); `rrc_frame_rx_reset()` is the idle-timeout release. Maximum record length is a parameter (`RRC_HEAD_MAX_RECORD` 8192, `RRC_CHASSIS_MAX_RECORD` 2048). |
| `rrc_json_writer.h` | Bounded JSON writer, output byte-identical to Python `json.dumps(separators=(",", ":"), ensure_ascii=False)`. Overflow or misuse latches an error and never writes past the buffer; check `rrc_jw_ok()` once at the end. `rrc_jw_fixed()` prints decimal fixed point without floating point. |
| `rrc_json_reader.h` | Strict validating reader into a caller-supplied token array. Rejects duplicate keys (compared after unescaping), invalid UTF-8, unpaired surrogates, non-RFC numbers, trailing bytes, and anything beyond the depth / string-length / token limits you pass. Integer accessors refuse fractions, exponents and out-of-range values. |
| `rrc_envelope.h` | `REQ`/`RSP` envelope: `rrc_req_parse()` (classifies INVALID → discard, BAD_VERSION → answer `UNSUPPORTED`, BAD_SHAPE → answer `BAD_ARG`, OK), `rrc_rsp_begin()/end()`, `rrc_req_begin()/end()`, and the last-transaction reply cache `rrc_reply_cache_t`. |
| `rrc_clock.h` | 32→64-bit counter extension, overflow-safe `rrc_muldiv_u64`, tick↔µs conversion, saturating deadline helpers. Reads no clock itself. |
| `rrc_ring.h` | SPSC byte ring (ISR → main loop), power-of-two capacity, drop counter. |
| `rrc_uuid.h` | UUIDv4 from an entropy callback; canonical-form check. |
| `rrc_sha256.h` | Streaming SHA-256 and lowercase hex. |
| `rrc_base64.h` | Base64 encode and strict decode. |

## Typical receive / reply path (both links)

```c
static uint8_t rx_buf[RRC_CHASSIS_MAX_RECORD], tx_buf[RRC_CHASSIS_MAX_RECORD];
static rrc_frame_rx_t rx;            /* rrc_frame_rx_init(&rx, rx_buf, sizeof rx_buf) once */
static rrc_reply_cache_t cache;      /* rrc_cache_clear(&cache) once, and on every reset rule */

void on_byte(uint8_t b) {
    size_t json_len; uint32_t crc;
    if (rrc_frame_rx_push(&rx, b, &json_len, &crc) != RRC_RX_RECORD) return;   /* discards are silent */
    rrc_jtok_t tok[64]; rrc_json_t doc; rrc_req_t req;
    static const rrc_json_limits_t lim = {8, 256};
    if (rrc_json_parse(&doc, (const char *)rx_buf, json_len, tok, 64, &lim) != RRC_JSON_OK) return;
    rrc_req_status_t st = rrc_req_parse(&doc, "1.0", &req);
    if (st == RRC_REQ_INVALID) return;
    if (rrc_cache_hit(&cache, req.id, crc, json_len)) { send(tx_buf, cache.reply_len); return; }
    rrc_jw_t w; rrc_jw_init(&w, (char *)tx_buf, sizeof tx_buf - RRC_FRAME_TRAILER_LEN);
    if (st == RRC_REQ_BAD_VERSION)      rrc_rsp_empty(&w, "1.0", req.id, "UNSUPPORTED");
    else if (st == RRC_REQ_BAD_SHAPE)   rrc_rsp_empty(&w, "1.0", req.id, "BAD_ARG");
    else { rrc_rsp_begin(&w, "1.0", req.id, "OK"); /* ...body object... */ rrc_rsp_end(&w); }
    size_t n = rrc_jw_ok(&w) ? rrc_frame_finish(tx_buf, rrc_jw_len(&w), sizeof tx_buf, sizeof tx_buf) : 0;
    if (n) { rrc_cache_store(&cache, req.id, crc, json_len, n); send(tx_buf, n); }
}
```

Reply-cache rule: a request is a *retry* only if its id **and** its exact JSON bytes (length and
CRC-32) equal those of the last completed transaction; then the stored reply bytes are sent again
unchanged. A different request that reuses an id is executed normally. The reply bytes stay in
the caller's transmit buffer; the cache structure only remembers what they answer.

## Limits and deliberate strictness

- The reader is stricter than Python's `json` in one place: unpaired `\uD800`-style surrogate
  escapes are rejected. Everything else the baseline `interface/wire_codec.py` accepts is
  accepted and vice versa (differential test below).
- Numbers are not converted to floating point anywhere in this library.
- Token indices are `int`; a document may hold at most 32767 tokens.

## Build and test (host)

```sh
cmake -S firmware/common -B build/common -G Ninja        # ASan + UBSan on by default
cmake --build build/common -j2
ctest --test-dir build/common --output-on-failure
```

Compiler flags: `-std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow -Wpedantic`.

- `tests/test_common.c` — unit tests for every module (known-answer vectors for CRC-32, SHA-256,
  base64; framing discard rules; reader rejection corpus; duplicate keys; limits; cache rule).
- `tests/test_interop.py` + `tests/rrc_codec_tool.c` — differential tests against the unmodified
  baseline `interface/wire_codec.py`: 3000 random objects re-encoded byte-identically by the C
  reader/writer/framer, and ~6000 randomly corrupted lines on which the C receiver must reach the
  same accept/reject verdict as `wire_codec.decode`.

To embed in another build, add `src/*.c` and `include/` (CMake: `add_subdirectory(firmware/common)`
and link `rr_common`; PlatformIO: see `firmware/head/platformio.ini`).

// Rad Roomba head event logic - one event chain (floor: LLD/ULD/ALPHA, reference: LLD/ULD)
//
// Tick convention: "tick t" is the clock period during which the 64-bit tick counter reads t. Inputs lld/uld/alpha
// are the synchronised levels valid during tick t; every register below takes its new value at the end of tick t.
//
//   state     meaning                                  live?  leaves when
//   IDLE      able to accept an LLD rising edge         yes   lld rises (event accepted on that tick, tick k)
//                                                             | alpha high with no LLD edge (orphan) -> WAITLOW
//   WINDOW    acceptance window, ticks k+1 .. k+W       no    after W ticks: classify on tick k+W
//   HOLD      fixed hold-off, ticks k+W+1 .. k+W+H      no    after H ticks (skipped when H = 0)
//   WAITLOW   wait for lld (and alpha) low, >= 1 tick   no    first tick on which lld = 0 (and alpha = 0)
//
//   ULD and ALPHA are latched if high on any tick k .. k+W. Class at tick k+W:
//      ALPHA latched -> class 2 (alpha) ; else ULD latched -> class 1 (reject) ; else class 0 (beta window / ref).
//   Dead ticks per isolated event = W + H + 1 (+ the ticks WAITLOW has to wait). Non-retriggerable: nothing that
//   happens on lld during WINDOW/HOLD restarts or lengthens them; only WAITLOW extends, and only while the inputs
//   are actually high.
//   BASELINE_STUCK: WAITLOW entered on tick t0 with the inputs still high on every tick t0 .. t0+S sets `stuck`
//   from tick t0+S+1 until the inputs go low. The chain stays dead (honest live time), it is never forced idle.
//
// Gate handling: `ld` is the first tick of a gate. A classification on tick t belongs to the gate containing t;
// a tick is live for the gate containing it. Counting is done by the accumulator server in hevt_core from
// evt_done/evt_class (one increment per event) and `dead` (one tick tally per chain).
`default_nettype none
module hevt_chain #(
    parameter HAS_ALPHA = 1
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              en,               // chain enabled (0: inputs are gated off outside, no live time)
    input  wire              lld,
    input  wire              uld,
    input  wire              alpha,
    input  wire [12:0]       cfg_win_m1,       // W - 1
    input  wire [15:0]       cfg_hold_m1,      // H - 1
    input  wire              cfg_hold_zero,    // H == 0
    input  wire [15:0]       cfg_stuck,        // S
    input  wire              cfg_wait_alpha,
    input  wire              ld,               // first tick of a gate
    output wire              evt_start,        // 1 on the tick an event is accepted
    output wire              evt_done,         // 1 on the classification tick
    output wire [1:0]        evt_class,        // valid with evt_done
    output wire              busy,             // not idle
    output reg               stuck,
    output wire              orphan_evt,
    output wire              dead,             // this tick is not a live tick (busy, or chain disabled)
    output reg  [7:0]        sh_orphan,        // shadow: orphan count of the gate that ended
    output reg  [2:0]        sh_flags          // shadow: {BUSY_AT_END, ORPHAN, STUCK}
);
    localparam [1:0] S_IDLE = 2'd0, S_WIN = 2'd1, S_HOLD = 2'd2, S_WAIT = 2'd3;

    reg [1:0]  state;
    reg [15:0] tmr;            // ticks spent in the current state (0 on its first tick)
    reg        lld_d, alpha_d;
    reg        got_uld, got_alpha;

    wire alpha_i   = (HAS_ALPHA != 0) ? alpha : 1'b0;
    wire lld_rise  = lld & ~lld_d;
    wire idle      = (state == S_IDLE);
    wire in_high   = lld | (cfg_wait_alpha & alpha_i);
    wire eq_w      = (tmr[12:0] == cfg_win_m1);     // last tick of WINDOW
    wire eq_h      = (tmr == cfg_hold_m1);          // last tick of HOLD
    wire eq_s      = (tmr == cfg_stuck);            // WAITLOW has lasted S ticks beyond its first

    assign evt_start  = idle & lld_rise;
    assign orphan_evt = idle & ~lld_rise & alpha_i & ~alpha_d;
    assign evt_done   = (state == S_WIN) & eq_w;
    wire   a_now      = got_alpha | alpha_i;
    wire   u_now      = got_uld | uld;
    assign evt_class  = a_now ? 2'd2 : (u_now ? 2'd1 : 2'd0);
    assign busy       = ~idle;

    always @(posedge clk) begin
        if (rst) begin
            state     <= S_WAIT;       // start dead: go idle only once the inputs are seen low
            tmr       <= 16'd0;
            lld_d     <= 1'b0;
            alpha_d   <= 1'b0;
            got_uld   <= 1'b0;
            got_alpha <= 1'b0;
            stuck     <= 1'b0;
        end else begin
            lld_d   <= lld;
            alpha_d <= alpha_i;
            case (state)
                S_IDLE: begin
                    stuck <= 1'b0;
                    tmr   <= 16'd0;
                    if (lld_rise) begin
                        state     <= S_WIN;
                        got_uld   <= uld;
                        got_alpha <= alpha_i;
                    end else if (cfg_wait_alpha & alpha_i) begin
                        state <= S_WAIT;
                    end
                end
                S_WIN: begin
                    got_uld   <= u_now;
                    got_alpha <= a_now;
                    if (eq_w) begin
                        state <= cfg_hold_zero ? S_WAIT : S_HOLD;
                        tmr   <= 16'd0;
                    end else begin
                        tmr <= tmr + 16'd1;
                    end
                end
                S_HOLD: begin
                    if (eq_h) begin
                        state <= S_WAIT;
                        tmr   <= 16'd0;
                    end else begin
                        tmr <= tmr + 16'd1;
                    end
                end
                default: begin // S_WAIT
                    if (!in_high) begin
                        state <= S_IDLE;
                        stuck <= 1'b0;
                        tmr   <= 16'd0;
                    end else if (eq_s) begin
                        stuck <= 1'b1;
                    end else if (!stuck) begin
                        tmr <= tmr + 16'd1;
                    end
                end
            endcase
        end
    end

    // ---------------------------------------------------------------- per-gate diagnostics
    // Event counts and dead ticks are accumulated outside (hevt_core accumulator server). Here: the sticky
    // per-gate flags and the orphan counter, copied to a shadow on `ld` (first tick of the next gate).
    reg [7:0] orphan_cnt;
    reg       f_stuck, f_orphan, busy_d;

    assign dead = ~(idle & en);

    always @(posedge clk) begin
        if (rst) begin
            orphan_cnt <= 8'd0;
            f_stuck    <= 1'b0;
            f_orphan   <= 1'b0;
            busy_d     <= 1'b0;
            sh_orphan  <= 8'd0;
            sh_flags   <= 3'd0;
        end else begin
            busy_d <= busy;
            if (ld) begin
                sh_orphan  <= (HAS_ALPHA != 0) ? orphan_cnt : 8'd0;
                sh_flags   <= {busy_d, f_orphan, f_stuck};
                orphan_cnt <= {7'd0, orphan_evt};
                f_stuck    <= stuck;
                f_orphan   <= orphan_evt;
            end else begin
                orphan_cnt <= orphan_cnt + {7'd0, orphan_evt & ~(&orphan_cnt)};
                f_stuck    <= f_stuck | stuck;
                f_orphan   <= f_orphan | orphan_evt;
            end
        end
    end
endmodule
`default_nettype wire

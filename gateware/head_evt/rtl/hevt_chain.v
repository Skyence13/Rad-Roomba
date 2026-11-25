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
// Gate handling: on the tick with gate_last = 1 every counter value *including this tick's increment* is copied
// to the l_* outputs and the counter restarts from zero, so each tick and each classification belongs to exactly
// one gate.
//
// Counters are CNT_W+1 bits and stop at 2^CNT_W (flag CNT_SAT). The live counter cannot overflow: a gate is at
// most 48,000,000 ticks < 2^26.
`default_nettype none
module hevt_chain #(
    parameter HAS_ALPHA = 1,
    parameter CNT_W     = 24,
    parameter LIVE_W    = 26
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              en,               // chain enabled (0: inputs are gated off outside, no live time)
    input  wire              lld,
    input  wire              uld,
    input  wire              alpha,
    input  wire [20:0]       cfg_win_ld,       // W - 2
    input  wire [20:0]       cfg_hold_ld,      // H - 2
    input  wire              cfg_hold_zero,    // H == 0
    input  wire [20:0]       cfg_stuck_ld,     // S - 1
    input  wire              cfg_wait_alpha,
    input  wire              gate_last,
    output wire              evt_start,        // 1 on the tick an event is accepted
    output wire              evt_done,         // 1 on the classification tick
    output wire [1:0]        evt_class,        // valid with evt_done
    output wire              busy,             // not idle
    output reg               stuck,
    output wire              orphan_evt,
    output wire              sat_now,
    output reg  [CNT_W:0]    l_c0,             // beta-window / ref
    output reg  [CNT_W:0]    l_c1,             // reject
    output reg  [CNT_W:0]    l_c2,             // alpha (floor only)
    output reg  [LIVE_W-1:0] l_live,
    output reg  [7:0]        l_orphan,
    output reg  [4:0]        l_flags           // {DISABLED, BUSY_AT_END, ORPHAN, STUCK, CNT_SAT}
);
    localparam [1:0] S_IDLE = 2'd0, S_WIN = 2'd1, S_HOLD = 2'd2, S_WAIT = 2'd3;

    reg [1:0]  state;
    reg [20:0] tmr;            // counts down; bit 20 set = expired
    reg        lld_d, alpha_d;
    reg        got_uld, got_alpha;

    wire alpha_i   = (HAS_ALPHA != 0) ? alpha : 1'b0;
    wire lld_rise  = lld & ~lld_d;
    wire tmr_exp   = tmr[20];
    wire idle      = (state == S_IDLE);
    wire in_high   = lld | (cfg_wait_alpha & alpha_i);

    assign evt_start  = idle & lld_rise;
    assign orphan_evt = idle & ~lld_rise & alpha_i & ~alpha_d;
    assign evt_done   = (state == S_WIN) & tmr_exp;
    wire   a_now      = got_alpha | alpha_i;
    wire   u_now      = got_uld | uld;
    assign evt_class  = a_now ? 2'd2 : (u_now ? 2'd1 : 2'd0);
    assign busy       = ~idle;

    always @(posedge clk) begin
        if (rst) begin
            state     <= S_WAIT;       // start dead: go idle only once the inputs are seen low
            tmr       <= 21'd0;
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
                    if (lld_rise) begin
                        state     <= S_WIN;
                        tmr       <= cfg_win_ld;
                        got_uld   <= uld;
                        got_alpha <= alpha_i;
                    end else if (cfg_wait_alpha & alpha_i) begin
                        state <= S_WAIT;
                        tmr   <= cfg_stuck_ld;
                    end
                end
                S_WIN: begin
                    got_uld   <= u_now;
                    got_alpha <= a_now;
                    if (tmr_exp) begin
                        if (cfg_hold_zero) begin
                            state <= S_WAIT;
                            tmr   <= cfg_stuck_ld;
                        end else begin
                            state <= S_HOLD;
                            tmr   <= cfg_hold_ld;
                        end
                    end else begin
                        tmr <= tmr - 21'd1;
                    end
                end
                S_HOLD: begin
                    if (tmr_exp) begin
                        state <= S_WAIT;
                        tmr   <= cfg_stuck_ld;
                    end else begin
                        tmr <= tmr - 21'd1;
                    end
                end
                default: begin // S_WAIT
                    if (!in_high) begin
                        state <= S_IDLE;
                        stuck <= 1'b0;
                    end else if (tmr_exp) begin
                        stuck <= 1'b1;
                    end else begin
                        tmr <= tmr - 21'd1;
                    end
                end
            endcase
        end
    end

    // ---------------------------------------------------------------- per-gate counters
    reg [CNT_W:0]    c0, c1, c2;
    reg [LIVE_W-1:0] live;
    reg [7:0]        orphan_cnt;
    reg              f_stuck, f_orphan;

    wire inc0 = evt_done & (evt_class == 2'd0);
    wire inc1 = evt_done & (evt_class == 2'd1);
    wire inc2 = evt_done & (evt_class == 2'd2);

    wire [CNT_W:0] c0_n = c0 + {{CNT_W{1'b0}}, inc0 & ~c0[CNT_W]};
    wire [CNT_W:0] c1_n = c1 + {{CNT_W{1'b0}}, inc1 & ~c1[CNT_W]};
    wire [CNT_W:0] c2_n = c2 + {{CNT_W{1'b0}}, inc2 & ~c2[CNT_W]};
    wire [LIVE_W-1:0] live_n = live + {{(LIVE_W-1){1'b0}}, idle & en};
    wire [7:0] orphan_n = orphan_cnt + {7'd0, orphan_evt & ~(&orphan_cnt)};
    wire       f_stuck_n  = f_stuck | stuck;
    wire       f_orphan_n = f_orphan | orphan_evt;

    assign sat_now = (inc0 & c0[CNT_W]) | (inc1 & c1[CNT_W]) | (inc2 & c2[CNT_W]);

    always @(posedge clk) begin
        if (rst | gate_last) begin
            c0         <= {(CNT_W+1){1'b0}};
            c1         <= {(CNT_W+1){1'b0}};
            c2         <= {(CNT_W+1){1'b0}};
            live       <= {LIVE_W{1'b0}};
            orphan_cnt <= 8'd0;
            f_stuck    <= 1'b0;
            f_orphan   <= 1'b0;
        end else begin
            c0         <= c0_n;
            c1         <= c1_n;
            c2         <= (HAS_ALPHA != 0) ? c2_n : {(CNT_W+1){1'b0}};
            live       <= live_n;
            orphan_cnt <= orphan_n;
            f_stuck    <= f_stuck_n;
            f_orphan   <= f_orphan_n;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            l_c0     <= {(CNT_W+1){1'b0}};
            l_c1     <= {(CNT_W+1){1'b0}};
            l_c2     <= {(CNT_W+1){1'b0}};
            l_live   <= {LIVE_W{1'b0}};
            l_orphan <= 8'd0;
            l_flags  <= 5'd0;
        end else if (gate_last) begin
            l_c0     <= c0_n;
            l_c1     <= c1_n;
            l_c2     <= (HAS_ALPHA != 0) ? c2_n : {(CNT_W+1){1'b0}};
            l_live   <= live_n;
            l_orphan <= orphan_n;
            l_flags  <= {~en, busy, f_orphan_n, f_stuck_n,
                         c0_n[CNT_W] | c1_n[CNT_W] | ((HAS_ALPHA != 0) & c2_n[CNT_W])};
        end
    end
endmodule
`default_nettype wire

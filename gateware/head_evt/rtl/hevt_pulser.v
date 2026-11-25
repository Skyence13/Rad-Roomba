// Rad Roomba head event logic - test pulser and self-test pattern generator
//
// Pulser
//   (re)start on `restart` (CTRL.PULSER_START, a PULSER_CFG write with EN = 1, or - with GATE_SYNC - the last tick
//   of every gate). With the restart strobe on tick r:
//     periodic: fire decisions on ticks r+1+PHASE, r+1+PHASE+PERIOD, ...; the output rises one tick after a decision
//               (so with GATE_SYNC the output rises on tick PHASE+1 of the gate, counting the first tick as 0).
//     random:   a fire decision on every tick on which xorshift32 state < PROB (Bernoulli trial per tick,
//               i.e. geometric = discretised exponential intervals, mean rate PROB * tick_hz / 2^32).
//   A decision is honoured only if the output is low and was low on the previous tick (minimum spacing WIDTH + 1
//   ticks start to start ... WIDTH high, >= 1 low) and the burst counter is not exhausted; otherwise it is dropped.
//   `rise` = 1 on the first tick of every output pulse (this is what PULSER_COUNT counts).
//
// Self-test pattern (digital loopback), launched by every pulse, starting on the tick the output rises:
//   LLD   high for LLD_W ticks
//   ULD   same as LLD when the pulse class is 1 or 2
//   ALPHA rises ALPHA_DLY ticks after LLD and stays high ALPHA_W ticks when the class is 2
//   class = SELFTEST.CLASS, or 0,1,2,0,1,2... per pulse when CLASS = 3 (restarts with the pulser sequence).
//   The pattern signals are registers (glitch-free) and go through the same front end as the comparator pins.
`default_nettype none
module hevt_pulser (
    input  wire        clk,
    input  wire        rst,
    input  wire        cfg_en,
    input  wire        cfg_random,
    input  wire [7:0]  cfg_width,
    input  wire [25:0] cfg_period,
    input  wire [25:0] cfg_phase,
    input  wire [15:0] cfg_burst,
    input  wire [31:0] cfg_prob,
    input  wire [31:0] cfg_seed,
    input  wire        restart,          // start / restart sequence
    input  wire        reseed,           // with restart: reload the random generator
    input  wire        stop,
    input  wire [1:0]  st_class,
    input  wire [7:0]  st_lld_w,
    input  wire [7:0]  st_alpha_dly,
    input  wire [15:0] st_alpha_w,
    output reg         out,              // pulse level
    output wire        rise,             // first tick of a pulse
    output wire        active,
    output reg         st_lld,
    output reg         st_uld,
    output reg         st_alpha
);
    reg        running;
    reg [25:0] pcnt;
    reg [15:0] bleft;
    reg        unlimited;
    reg [7:0]  wcnt;
    reg        recov;
    reg        out_d;
    reg [31:0] x;
    reg        rnd_hit;
    reg [1:0]  rot;

    // xorshift32 (Marsaglia 13,17,5): one full step per tick
    wire [31:0] x1 = x ^ (x << 13);
    wire [31:0] x2 = x1 ^ (x1 >> 17);
    wire [31:0] x3 = x2 ^ (x2 << 5);
    wire [31:0] seed_eff = (cfg_seed == 32'd0) ? 32'h1F2E3D4C : cfg_seed;

    wire [7:0] width_eff = (cfg_width == 8'd0) ? 8'd1 : cfg_width;
    wire want_fire = cfg_random ? rnd_hit : (pcnt == 26'd0);
    wire can_fire  = ~out & ~recov & (unlimited | (bleft != 16'd0));
    wire fire      = running & want_fire & can_fire;

    assign rise   = out & ~out_d;
    assign active = cfg_en & running & (unlimited | (bleft != 16'd0));

    always @(posedge clk) begin
        if (rst) begin
            running   <= 1'b0;
            pcnt      <= 26'd0;
            bleft     <= 16'd0;
            unlimited <= 1'b0;
            wcnt      <= 8'd0;
            recov     <= 1'b0;
            out       <= 1'b0;
            out_d     <= 1'b0;
            x         <= 32'h1F2E3D4C;
            rnd_hit   <= 1'b0;
        end else begin
            out_d   <= out;
            recov   <= 1'b0;
            x       <= x3;
            rnd_hit <= (x3 < cfg_prob);

            // output pulse timing
            if (out) begin
                if (wcnt == 8'd0) begin
                    out   <= 1'b0;
                    recov <= 1'b1;
                end else begin
                    wcnt <= wcnt - 8'd1;
                end
            end

            if (!cfg_en) begin
                running <= 1'b0;
                out     <= 1'b0;
                rnd_hit <= 1'b0;
            end else if (restart) begin
                running   <= 1'b1;
                pcnt      <= cfg_phase;
                bleft     <= cfg_burst;
                unlimited <= (cfg_burst == 16'd0);
                rnd_hit   <= 1'b0;
                if (reseed)
                    x <= seed_eff;
            end else if (stop) begin
                running <= 1'b0;
            end else if (running) begin
                if (!cfg_random) begin
                    if (pcnt == 26'd0)
                        pcnt <= cfg_period - 26'd1;
                    else
                        pcnt <= pcnt - 26'd1;
                end
                if (fire) begin
                    out   <= 1'b1;
                    wcnt  <= width_eff - 8'd1;
                    if (!unlimited)
                        bleft <= bleft - 16'd1;
                end
            end
        end
    end

    // ---------------------------------------------------------------- self-test pattern
    reg [7:0]  lld_cnt;
    reg [7:0]  dly_cnt;
    reg        dly_run;
    reg [15:0] a_cnt;
    wire [1:0] cls = (st_class == 2'd3) ? rot : st_class;
    wire [7:0]  lld_w_eff = (st_lld_w == 8'd0) ? 8'd1 : st_lld_w;
    wire [15:0] a_w_eff   = (st_alpha_w == 16'd0) ? 16'd1 : st_alpha_w;

    always @(posedge clk) begin
        if (rst) begin
            st_lld   <= 1'b0;
            st_uld   <= 1'b0;
            st_alpha <= 1'b0;
            lld_cnt  <= 8'd0;
            dly_cnt  <= 8'd0;
            dly_run  <= 1'b0;
            a_cnt    <= 16'd0;
            rot      <= 2'd0;
        end else begin
            // LLD / ULD
            if (st_lld) begin
                if (lld_cnt == 8'd0) begin
                    st_lld <= 1'b0;
                    st_uld <= 1'b0;
                end else begin
                    lld_cnt <= lld_cnt - 8'd1;
                end
            end
            // ALPHA delay and width
            if (st_alpha) begin
                if (a_cnt == 16'd0)
                    st_alpha <= 1'b0;
                else
                    a_cnt <= a_cnt - 16'd1;
            end
            if (dly_run) begin
                if (dly_cnt == 8'd0) begin
                    dly_run  <= 1'b0;
                    st_alpha <= 1'b1;
                    a_cnt    <= a_w_eff - 16'd1;
                end else begin
                    dly_cnt <= dly_cnt - 8'd1;
                end
            end
            // launch: `fire` is the tick before the pulser output rises, so the pattern registers rise with it
            if (fire) begin
                st_lld  <= 1'b1;
                st_uld  <= (cls != 2'd0);
                lld_cnt <= lld_w_eff - 8'd1;
                if (cls == 2'd2) begin
                    if (st_alpha_dly == 8'd0) begin
                        st_alpha <= 1'b1;
                        a_cnt    <= a_w_eff - 16'd1;
                        dly_run  <= 1'b0;
                    end else begin
                        dly_run <= 1'b1;
                        dly_cnt <= st_alpha_dly - 8'd1;
                    end
                end
                rot <= (rot == 2'd2) ? 2'd0 : rot + 2'd1;
            end
            if (restart || !cfg_en)
                rot <= 2'd0;
        end
    end
endmodule
`default_nettype wire

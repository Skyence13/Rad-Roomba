// Rad Roomba head event logic - core (everything except PLL and pads)
// Single clock domain `clk` (tick clock, 48 MHz). `rst` is a synchronous power-on reset.
// See regmap.yaml for the register interface and README.md for the timing definitions.
`default_nettype none
`include "head_evt_regs.vh"
`ifndef HEVT_BUILD_ID
`define HEVT_BUILD_ID 32'h00000000
`endif
module hevt_core #(
    parameter CNT_W = 21
) (
    input  wire        clk,
    input  wire        rst,
    // comparator inputs (asynchronous, active high)
    input  wire [3:0]  beta_lld,
    input  wire [3:0]  beta_uld,
    input  wire [3:0]  alpha,
    input  wire [3:0]  ref_lld,
    input  wire [3:0]  ref_uld,
    // SPI slave
    input  wire        spi_sck,
    input  wire        spi_cs_n,
    input  wire        spi_mosi,
    output wire        spi_miso,
    // misc I/O
    input  wire        htr_state,
    input  wire        sync_in,
    output reg         irq,
    output reg         trig_out,
    output reg         pulser,
    output reg         gate_sync,
    output reg         htr_sync,
    output reg         led
);
    localparam [3:0] FIFO_DEPTH = 4'd8;
    localparam [5:0] REC_LAST = 6'd47;

    // ------------------------------------------------------------------ soft reset
    // rst_i: power-on or soft reset (SPI, registers). rst_x: the same, stretched while the accumulator RAM is
    // being cleared (128 ticks); everything that takes part in acquisition is held in reset until then.
    reg  srst;
    wire rst_i = rst | srst;
    reg        init_run;
    reg [6:0]  init_cnt;
    always @(posedge clk) begin
        if (rst_i) begin
            init_run <= 1'b1;
            init_cnt <= 7'd0;
        end else if (init_run) begin
            init_cnt <= init_cnt + 7'd1;
            if (init_cnt == 7'd127)
                init_run <= 1'b0;
        end
    end
    wire rst_x = rst_i | init_run;

    // ------------------------------------------------------------------ 64-bit tick counter (two 32-bit halves,
    // carry pre-decoded one tick ahead so {tick_hi, tick_lo} is always a coherent 64-bit value)
    reg [31:0] tick_lo /* verilator public_flat */;
    reg [31:0] tick_hi /* verilator public_flat */;
    reg        lo_wrap /* verilator public_flat */;
    always @(posedge clk) begin
        if (rst) begin
            tick_lo <= 32'd0;
            tick_hi <= 32'd0;
            lo_wrap <= 1'b0;
        end else begin
            tick_lo <= tick_lo + 32'd1;
            lo_wrap <= (tick_lo == 32'hFFFF_FFFE);
            if (lo_wrap)
                tick_hi <= tick_hi + 32'd1;
        end
    end

    // ------------------------------------------------------------------ SPI
    wire        spi_cs_fall, spi_rd_req, spi_wr_raw, spi_frame_err;
    reg         spi_wr_stb;       // spi_wr_raw one tick later, together with the registered range check
    wire [6:0]  spi_addr, spi_wr_addr;
    wire [31:0] spi_wr_data;
    wire [31:0] rd_data;
    wire [7:0]  status_byte;

    hevt_spi u_spi (
        .clk(clk), .rst(rst_i),
        .sck(spi_sck), .cs_n(spi_cs_n), .mosi(spi_mosi), .miso(spi_miso),
        .status_byte(status_byte),
        .cs_fall(spi_cs_fall), .rd_req(spi_rd_req), .addr(spi_addr), .rd_data(rd_data),
        .wr_stb(spi_wr_raw), .wr_addr(spi_wr_addr), .wr_data(spi_wr_data),
        .frame_err(spi_frame_err)
    );

    // ------------------------------------------------------------------ configuration registers
    reg [25:0] cfg_gate_ticks;
    reg [12:0] cfg_fwin, cfg_rwin;
    reg [15:0] cfg_fhold, cfg_rhold;
    reg [15:0] cfg_fstuck, cfg_rstuck;
    reg        fe_sync_only, fe_wait_alpha;
    reg [7:0]  fe_chain_en;
    reg        st_en;
    reg [1:0]  st_class;
    reg [7:0]  st_mask;
    reg [7:0]  st_lld_w, st_alpha_dly;
    reg [15:0] st_alpha_w;
    reg        pul_en, pul_random, pul_gsync, pul_outen;
    reg [7:0]  pul_width;
    reg [25:0] pul_period, pul_phase;
    reg [15:0] pul_burst;
    reg [31:0] pul_prob, setup_tag;
    reg        htr_src;
    // run-time registers
    reg [2:0]  irq_en;
    reg [31:0] scratch;
    reg [23:0] trig_cfg;
    reg        htr_req;
    reg [1:0]  led_mode;

    // read-back image of the frozen block, index 0..17 = address 0x10..0x21 (this is what CFG_CRC covers)
    function [31:0] cfgw;
        input [4:0] i;
        begin
            case (i)
                5'd0:  cfgw = {6'd0, cfg_gate_ticks};
                5'd1:  cfgw = {19'd0, cfg_fwin};
                5'd2:  cfgw = {16'd0, cfg_fhold};
                5'd3:  cfgw = {16'd0, cfg_fstuck};
                5'd4:  cfgw = {19'd0, cfg_rwin};
                5'd5:  cfgw = {16'd0, cfg_rhold};
                5'd6:  cfgw = {16'd0, cfg_rstuck};
                5'd7:  cfgw = {16'd0, fe_chain_en, 6'd0, fe_wait_alpha, fe_sync_only};
                5'd8:  cfgw = {16'd0, st_mask, 5'd0, st_class, st_en};
                5'd9:  cfgw = {st_alpha_w, st_alpha_dly, st_lld_w};
                5'd10: cfgw = {16'd0, pul_width, 4'd0, pul_outen, pul_gsync, pul_random, pul_en};
                5'd11: cfgw = {6'd0, pul_period};
                5'd12: cfgw = {6'd0, pul_phase};
                5'd13: cfgw = {16'd0, pul_burst};
                5'd14: cfgw = pul_prob;
                5'd15: cfgw = `HEVT_RST_PULSER_SEED;      // fixed seed in this version
                5'd16: cfgw = setup_tag;
                5'd17: cfgw = {31'd0, htr_src};
                default: cfgw = 32'd0;
            endcase
        end
    endfunction

    // state referenced by the register logic
    reg        armed, arm_pending, disarm_pending;
    reg        ser_run, ser_armed, commit;
    reg [3:0]  fifo_level;
    reg [2:0]  rd_slot, wr_slot;
    reg [15:0] lost_total;
    reg [31:0] seq;
    reg [9:0]  flags;
    reg        crc_valid;
    reg [31:0] crc;
    reg        gate_last;
    reg [25:0] gpos;
    reg        trig_fired;
    reg [2:0]  trig_chain, trig_src;
    reg [31:0] trig_tick;
    reg        sync_valid;
    reg [63:0] sync_tick;
    reg [15:0] sync_count;
    reg [63:0] snap_tick;
    reg        htr_state_s;
    reg        sync_in_s;
    wire [19:0] fe_q;
    wire [7:0] ch_busy, ch_stuck;
    integer k;
    wire       pul_active;

    wire locked  = armed | arm_pending | (ser_run & ser_armed);

    wire wr_is_cfg = spi_wr_stb && (spi_wr_addr >= `HEVT_CFG_FIRST) && (spi_wr_addr < (`HEVT_CFG_FIRST + `HEVT_CFG_COUNT));
    wire [31:0] wd = spi_wr_data;

    // one >= and one <= comparator, limits selected by address
    reg [25:0] lim_lo, lim_hi;
    always @(*) begin
        lim_lo = 26'd0;
        lim_hi = 26'h3FFFFFF;
        case (spi_wr_addr)
            `HEVT_A_GATE_TICKS:      begin lim_lo = `HEVT_MIN_GATE_TICKS;      lim_hi = `HEVT_MAX_GATE_TICKS;      end
            `HEVT_A_FLOOR_WINDOW:    begin lim_lo = `HEVT_MIN_FLOOR_WINDOW;    lim_hi = `HEVT_MAX_FLOOR_WINDOW;    end
            `HEVT_A_FLOOR_HOLDOFF:   begin lim_hi = `HEVT_MAX_FLOOR_HOLDOFF;   end
            `HEVT_A_FLOOR_STUCK_MAX: begin lim_lo = `HEVT_MIN_FLOOR_STUCK_MAX; lim_hi = `HEVT_MAX_FLOOR_STUCK_MAX; end
            `HEVT_A_REF_WINDOW:      begin lim_lo = `HEVT_MIN_REF_WINDOW;      lim_hi = `HEVT_MAX_REF_WINDOW;      end
            `HEVT_A_REF_HOLDOFF:     begin lim_hi = `HEVT_MAX_REF_HOLDOFF;     end
            `HEVT_A_REF_STUCK_MAX:   begin lim_lo = `HEVT_MIN_REF_STUCK_MAX;   lim_hi = `HEVT_MAX_REF_STUCK_MAX;   end
            `HEVT_A_PULSER_PERIOD:   begin lim_lo = `HEVT_MIN_PULSER_PERIOD;   lim_hi = `HEVT_MAX_PULSER_PERIOD;   end
            `HEVT_A_PULSER_PHASE:    begin lim_hi = `HEVT_MAX_PULSER_PHASE;    end
            `HEVT_A_PULSER_BURST:    begin lim_hi = `HEVT_MAX_PULSER_BURST;    end
            default: ;
        endcase
    end
    wire range_checked = (spi_wr_addr >= `HEVT_A_GATE_TICKS && spi_wr_addr <= `HEVT_A_REF_STUCK_MAX) ||
                         (spi_wr_addr >= `HEVT_A_PULSER_PERIOD && spi_wr_addr <= `HEVT_A_PULSER_BURST);
    // wr_addr/wr_data are stable for many ticks around the write strobe: the comparison is registered and the
    // strobe that acts on the registers is delayed by the same one tick.
    reg range_ok;
    always @(posedge clk) begin
        range_ok   <= ~range_checked | ((wd[31:26] == 6'd0) && (wd[25:0] >= lim_lo) && (wd[25:0] <= lim_hi));
        spi_wr_stb <= spi_wr_raw & ~rst_i;
    end

    wire cfg_accept = wr_is_cfg & ~locked & range_ok;
    wire cfg_rej    = wr_is_cfg & locked;
    wire cfg_bad    = wr_is_cfg & ~locked & ~range_ok;

    wire wr_ctrl       = spi_wr_stb && (spi_wr_addr == `HEVT_A_CTRL);
    wire ctrl_arm      = wr_ctrl & wd[`HEVT_CTRL_ARM_B] & ~wd[`HEVT_CTRL_DISARM_B];
    wire ctrl_disarm   = wr_ctrl & wd[`HEVT_CTRL_DISARM_B];
    wire ctrl_resync_r = wr_ctrl & wd[`HEVT_CTRL_GATE_RESYNC_B];
    wire ctrl_pop      = wr_ctrl & wd[`HEVT_CTRL_FIFO_POP_B];
    wire ctrl_flush    = wr_ctrl & wd[`HEVT_CTRL_FIFO_FLUSH_B];
    wire ctrl_seqclr_r = wr_ctrl & wd[`HEVT_CTRL_SEQ_CLEAR_B];
    wire ctrl_trig_rearm = wr_ctrl & wd[`HEVT_CTRL_TRIG_REARM_B];
    wire ctrl_sync_rearm = wr_ctrl & wd[`HEVT_CTRL_SYNC_REARM_B];
    wire ctrl_pul_start  = wr_ctrl & wd[`HEVT_CTRL_PULSER_START_B];
    wire ctrl_pul_stop   = wr_ctrl & wd[`HEVT_CTRL_PULSER_STOP_B];
    wire ctrl_srst       = wr_ctrl & wd[`HEVT_CTRL_SOFT_RESET_B] & (wd[`HEVT_CTRL_KEY_R] == `HEVT_CTRL_KEY_VALUE);
    wire ctrl_resync   = ctrl_resync_r & ~locked;
    wire ctrl_seqclr   = ctrl_seqclr_r & ~locked;
    wire ctrl_rej      = (ctrl_resync_r | ctrl_seqclr_r) & locked;

    wire pul_cfg_start = cfg_accept && (spi_wr_addr == `HEVT_A_PULSER_CFG) && wd[`HEVT_PULSER_CFG_EN_B];

    always @(posedge clk) begin
        srst <= 1'b0;
        if (rst_i) begin
            cfg_gate_ticks <= `HEVT_RSTW_GATE_TICKS;
            cfg_fwin       <= `HEVT_RSTW_FLOOR_WINDOW;
            cfg_fhold      <= `HEVT_RSTW_FLOOR_HOLDOFF;
            cfg_fstuck     <= `HEVT_RSTW_FLOOR_STUCK_MAX;
            cfg_rwin       <= `HEVT_RSTW_REF_WINDOW;
            cfg_rhold      <= `HEVT_RSTW_REF_HOLDOFF;
            cfg_rstuck     <= `HEVT_RSTW_REF_STUCK_MAX;
            {fe_chain_en, fe_wait_alpha, fe_sync_only} <= 10'b11111111_1_0;
            st_en <= 1'b0; st_class <= 2'd0; st_mask <= 8'd0;
            st_lld_w <= 8'd4; st_alpha_dly <= 8'd8; st_alpha_w <= 16'd96;
            pul_en <= 1'b0; pul_random <= 1'b0; pul_gsync <= 1'b0; pul_outen <= 1'b0;
            pul_width  <= 8'd4;
            pul_period <= `HEVT_RSTW_PULSER_PERIOD;
            pul_phase  <= 26'd0;
            pul_burst  <= 16'd0;
            pul_prob   <= `HEVT_RST_PULSER_PROB;
            setup_tag  <= 32'd0;
            htr_src    <= 1'b0;
            irq_en     <= 3'b001;
            scratch    <= 32'd0;
            trig_cfg   <= 24'h300000;
            htr_req    <= 1'b0;
            led_mode   <= 2'd1;
        end else begin
            if (ctrl_srst)
                srst <= 1'b1;
            if (cfg_accept) begin
                case (spi_wr_addr)
                    `HEVT_A_GATE_TICKS:      cfg_gate_ticks <= wd[25:0];
                    `HEVT_A_FLOOR_WINDOW:    cfg_fwin   <= wd[12:0];
                    `HEVT_A_FLOOR_HOLDOFF:   cfg_fhold  <= wd[15:0];
                    `HEVT_A_FLOOR_STUCK_MAX: cfg_fstuck <= wd[15:0];
                    `HEVT_A_REF_WINDOW:      cfg_rwin   <= wd[12:0];
                    `HEVT_A_REF_HOLDOFF:     cfg_rhold  <= wd[15:0];
                    `HEVT_A_REF_STUCK_MAX:   cfg_rstuck <= wd[15:0];
                    `HEVT_A_FE_CFG: begin
                        fe_sync_only  <= wd[`HEVT_FE_CFG_SYNC_ONLY_B];
                        fe_wait_alpha <= wd[`HEVT_FE_CFG_WAIT_ALPHA_LOW_B];
                        fe_chain_en   <= wd[`HEVT_FE_CFG_CHAIN_EN_R];
                    end
                    `HEVT_A_SELFTEST: begin
                        st_en    <= wd[`HEVT_SELFTEST_EN_B];
                        st_class <= wd[`HEVT_SELFTEST_CLASS_R];
                        st_mask  <= wd[`HEVT_SELFTEST_CHAIN_MASK_R];
                    end
                    `HEVT_A_ST_SHAPE: begin
                        st_lld_w     <= wd[`HEVT_ST_SHAPE_LLD_W_R];
                        st_alpha_dly <= wd[`HEVT_ST_SHAPE_ALPHA_DLY_R];
                        st_alpha_w   <= wd[`HEVT_ST_SHAPE_ALPHA_W_R];
                    end
                    `HEVT_A_PULSER_CFG: begin
                        pul_en     <= wd[`HEVT_PULSER_CFG_EN_B];
                        pul_random <= wd[`HEVT_PULSER_CFG_RANDOM_B];
                        pul_gsync  <= wd[`HEVT_PULSER_CFG_GATE_SYNC_B];
                        pul_outen  <= wd[`HEVT_PULSER_CFG_OUT_EN_B];
                        pul_width  <= wd[`HEVT_PULSER_CFG_WIDTH_R];
                    end
                    `HEVT_A_PULSER_PERIOD:   pul_period <= wd[25:0];
                    `HEVT_A_PULSER_PHASE:    pul_phase  <= wd[25:0];
                    `HEVT_A_PULSER_BURST:    pul_burst  <= wd[15:0];
                    `HEVT_A_PULSER_PROB:     pul_prob   <= wd;
                    `HEVT_A_SETUP_TAG:       setup_tag  <= wd;
                    `HEVT_A_HTR_CFG:         htr_src    <= wd[`HEVT_HTR_CFG_SRC_INTERNAL_B];
                    default: ;
                endcase
            end
            if (spi_wr_stb) begin
                case (spi_wr_addr)
                    `HEVT_A_IRQ_EN:   irq_en   <= wd[2:0];
                    `HEVT_A_SCRATCH:  scratch  <= wd;
                    `HEVT_A_TRIG_CFG: trig_cfg <= wd[23:0];
                    `HEVT_A_HTR_CTRL: htr_req  <= wd[`HEVT_HTR_CTRL_ON_B];
                    `HEVT_A_LED_CFG:  led_mode <= wd[`HEVT_LED_CFG_MODE_R];
                    default: ;
                endcase
            end
        end
    end

    // timer compare values for the chains (registered; the configuration is static while armed)
    reg [12:0] fwin_m1, rwin_m1;
    reg [15:0] fhold_m1, rhold_m1;
    reg        fhold_zero, rhold_zero;
    always @(posedge clk) begin
        fwin_m1    <= cfg_fwin  - 13'd1;
        fhold_m1   <= cfg_fhold - 16'd1;
        rwin_m1    <= cfg_rwin  - 13'd1;
        rhold_m1   <= cfg_rhold - 16'd1;
        fhold_zero <= (cfg_fhold == 16'd0);
        rhold_zero <= (cfg_rhold == 16'd0);
    end

    // ------------------------------------------------------------------ configuration CRC-32 (zlib), bit serial
    // One word multiplexer over the frozen block is shared by the SPI read path (priority) and the CRC engine.
    reg        crc_run, crc_ldw;
    reg [4:0]  crc_w, crc_b;
    reg [31:0] crc_sh;
    wire [4:0]  cfg_idx  = spi_rd_req ? (spi_addr[4:0] - 5'd16) : crc_w;
    wire [31:0] cfg_word = cfgw(cfg_idx);
    wire        crc_fb   = crc[0] ^ crc_sh[0];
    always @(posedge clk) begin
        if (rst_i | cfg_accept) begin
            crc_valid <= 1'b0;
            crc_run   <= 1'b0;
            crc_ldw   <= 1'b0;
            crc_w     <= 5'd0;
            crc_b     <= 5'd0;
            crc       <= 32'hFFFF_FFFF;
            crc_sh    <= 32'd0;
        end else if (!crc_run && !crc_valid) begin
            crc_run <= 1'b1;                 // one tick after the write: configuration registers are settled
            crc_ldw <= 1'b1;
            crc     <= 32'hFFFF_FFFF;
            crc_w   <= 5'd0;
            crc_b   <= 5'd0;
        end else if (crc_run && crc_ldw) begin
            if (!spi_rd_req) begin           // the SPI read path owns the multiplexer on this tick: retry
                crc_sh  <= cfg_word;
                crc_ldw <= 1'b0;
            end
        end else if (crc_run) begin
            crc    <= {1'b0, crc[31:1]} ^ (crc_fb ? 32'hEDB8_8320 : 32'd0);
            crc_sh <= {1'b0, crc_sh[31:1]};
            crc_b  <= crc_b + 5'd1;
            if (crc_b == 5'd31) begin
                crc_w   <= crc_w + 5'd1;
                crc_ldw <= 1'b1;
                if (crc_w == (`HEVT_CFG_COUNT - 1)) begin
                    crc_run   <= 1'b0;
                    crc_ldw   <= 1'b0;
                    crc_valid <= 1'b1;
                end
            end
        end
    end
    wire [31:0] cfg_crc = ~crc;

    // ------------------------------------------------------------------ gate generator
    // gate_last = last tick of a gate, gate_first (= ld) = first tick of the next one. `bank` selects the half of
    // the accumulator RAM that belongs to the gate in progress; it toggles together with gate_first.
    reg [25:0] n_cur_m2;
    reg        gate_first;
    reg        bank;
    reg        resync_pend;
    reg [63:0] gate_start;
    wire       ser_idle;
    always @(posedge clk) begin
        if (rst_x) begin
            gpos        <= 26'd0;
            n_cur_m2    <= `HEVT_RSTW_GATE_TICKS - 26'd2;
            gate_last   <= 1'b0;
            gate_first  <= 1'b1;
            gate_sync   <= 1'b0;
            bank        <= 1'b0;
            resync_pend <= 1'b0;
        end else begin
            gate_first <= gate_last;
            if (ctrl_resync)
                resync_pend <= 1'b1;
            if (gate_last) begin
                gpos        <= 26'd0;
                n_cur_m2    <= cfg_gate_ticks - 26'd2;
                gate_last   <= 1'b0;
                gate_sync   <= ~gate_sync;
                bank        <= ~bank;
                resync_pend <= 1'b0;
            end else begin
                gpos      <= gpos + 26'd1;
                // a resync waits (at most ~25 us) until the record pass of the previous gate has finished
                gate_last <= (gpos == n_cur_m2) | (resync_pend & ser_idle & ~gate_first);
            end
        end
    end
    always @(posedge clk) begin
        if (rst)
            gate_start <= 64'd0;
        else if (gate_first)
            gate_start <= {tick_hi, tick_lo};
    end
    wire ld = gate_first;      // first tick of a gate: totals of the previous gate are complete

    // ------------------------------------------------------------------ arm / disarm / sequence
    reg  first_gate;
    reg  armed_d, first_d, last_d;      // state of the gate that ended on the previous tick (valid on `ld`)
    wire ser_done;
    always @(posedge clk) begin
        if (rst_x) begin
            armed          <= 1'b0;
            arm_pending    <= 1'b0;
            disarm_pending <= 1'b0;
            first_gate     <= 1'b0;
            seq            <= 32'd0;
            armed_d        <= 1'b0;
            first_d        <= 1'b0;
            last_d         <= 1'b0;
        end else begin
            armed_d <= armed;
            first_d <= first_gate;
            last_d  <= disarm_pending;
            if (ctrl_disarm) begin
                arm_pending <= 1'b0;
                if (armed)
                    disarm_pending <= 1'b1;
            end else if (ctrl_arm) begin
                arm_pending <= ~armed | disarm_pending;
            end
            if (ctrl_seqclr)
                seq <= 32'd0;
            if (ser_done && ser_armed)      // the record pass of an armed gate has finished (stored or dropped)
                seq <= seq + 32'd1;
            if (gate_last) begin
                if (armed) begin
                    first_gate <= 1'b0;
                    if (disarm_pending) begin
                        armed          <= 1'b0;
                        disarm_pending <= 1'b0;
                    end
                end else if (arm_pending && crc_valid && !ctrl_disarm) begin
                    armed       <= 1'b1;
                    arm_pending <= 1'b0;
                    first_gate  <= 1'b1;
                end
            end
        end
    end

    // ------------------------------------------------------------------ pulser and self-test pattern
    wire pul_out, pul_rise, st_lld, st_uld, st_alpha;
    reg  pul_stopped;
    wire pul_gate_restart = pul_gsync & gate_last & ~pul_stopped;
    always @(posedge clk) begin
        if (rst_x)
            pul_stopped <= 1'b0;
        else if (ctrl_pul_start | pul_cfg_start)
            pul_stopped <= 1'b0;
        else if (ctrl_pul_stop)
            pul_stopped <= 1'b1;
    end

    hevt_pulser u_pulser (
        .clk(clk), .rst(rst_x),
        .cfg_en(pul_en), .cfg_random(pul_random), .cfg_width(pul_width), .cfg_period(pul_period),
        .cfg_phase(pul_phase), .cfg_burst(pul_burst), .cfg_prob(pul_prob),
        .restart(ctrl_pul_start | pul_cfg_start | pul_gate_restart),
        .reseed(ctrl_pul_start | pul_cfg_start),
        .stop(ctrl_pul_stop),
        .st_class(st_class), .st_lld_w(st_lld_w), .st_alpha_dly(st_alpha_dly), .st_alpha_w(st_alpha_w),
        .out(pul_out), .rise(pul_rise), .active(pul_active),
        .st_lld(st_lld), .st_uld(st_uld), .st_alpha(st_alpha)
    );

    always @(posedge clk) begin
        if (rst_x)
            pulser <= 1'b0;
        else
            pulser <= pul_out & pul_outen;   // pin lags the internal pulse by one tick
    end

    // ------------------------------------------------------------------ front ends
    // fe_in order = IN_LEVELS: [3:0] BETA_LLD, [7:4] BETA_ULD, [11:8] ALPHA, [15:12] REF_LLD, [19:16] REF_ULD
    wire [19:0] pad_in = {ref_uld, ref_lld, alpha, beta_uld, beta_lld};
    wire [19:0] st_in  = {{4{st_uld}} & st_mask[7:4], {4{st_lld}} & st_mask[7:4],
                          {4{st_alpha}} & st_mask[3:0], {4{st_uld}} & st_mask[3:0], {4{st_lld}} & st_mask[3:0]};
    wire [19:0] en_in  = {fe_chain_en[7:4], fe_chain_en[7:4], fe_chain_en[3:0], fe_chain_en[3:0], fe_chain_en[3:0]};
    wire [19:0] fe_in /* verilator public_flat_rd */;
    assign fe_in = (st_en ? st_in : pad_in) & en_in;

    genvar gi;
    generate
        for (gi = 0; gi < 20; gi = gi + 1) begin : g_fe
            hevt_frontend u_fe (.clk(clk), .rst(rst_x), .d_async(fe_in[gi]), .sync_only(fe_sync_only), .q(fe_q[gi]));
        end
    endgenerate

    // ------------------------------------------------------------------ chains
    wire [7:0]  ch_start, ch_done, ch_orphan, ch_dead;
    wire [15:0] ch_class;
    wire [8*8-1:0] ch_sh_orphan;
    wire [8*3-1:0] ch_sh_flags;

    generate
        for (gi = 0; gi < 4; gi = gi + 1) begin : g_floor
            hevt_chain #(.HAS_ALPHA(1)) u_ch (
                .clk(clk), .rst(rst_x), .en(fe_chain_en[gi]),
                .lld(fe_q[gi]), .uld(fe_q[4+gi]), .alpha(fe_q[8+gi]),
                .cfg_win_m1(fwin_m1), .cfg_hold_m1(fhold_m1), .cfg_hold_zero(fhold_zero),
                .cfg_stuck(cfg_fstuck), .cfg_wait_alpha(fe_wait_alpha),
                .ld(ld),
                .evt_start(ch_start[gi]), .evt_done(ch_done[gi]), .evt_class(ch_class[2*gi +: 2]),
                .busy(ch_busy[gi]), .stuck(ch_stuck[gi]), .orphan_evt(ch_orphan[gi]), .dead(ch_dead[gi]),
                .sh_orphan(ch_sh_orphan[8*gi +: 8]), .sh_flags(ch_sh_flags[3*gi +: 3])
            );
        end
        for (gi = 4; gi < 8; gi = gi + 1) begin : g_ref
            hevt_chain #(.HAS_ALPHA(0)) u_ch (
                .clk(clk), .rst(rst_x), .en(fe_chain_en[gi]),
                .lld(fe_q[8+gi]), .uld(fe_q[12+gi]), .alpha(1'b0),
                .cfg_win_m1(rwin_m1), .cfg_hold_m1(rhold_m1), .cfg_hold_zero(rhold_zero),
                .cfg_stuck(cfg_rstuck), .cfg_wait_alpha(1'b0),
                .ld(ld),
                .evt_start(ch_start[gi]), .evt_done(ch_done[gi]), .evt_class(ch_class[2*gi +: 2]),
                .busy(ch_busy[gi]), .stuck(ch_stuck[gi]), .orphan_evt(ch_orphan[gi]), .dead(ch_dead[gi]),
                .sh_orphan(ch_sh_orphan[8*gi +: 8]), .sh_flags(ch_sh_flags[3*gi +: 3])
            );
        end
    endgenerate

    // ------------------------------------------------------------------ heater bookkeeping, SYNC_IN capture
    reg        htr_m, sync_m, sync_d;
    reg        h_d, h_start;
    reg [7:0]  tr_cnt;
    reg        f_sync;
    reg [7:0]  l_tr;
    reg        l_hs, l_he, l_sync, l_first, l_last;
    wire       h      = htr_src ? htr_sync : htr_state_s;
    wire       h_tr   = h ^ h_d;
    wire       sync_rise = sync_in_s & ~sync_d;

    always @(posedge clk) begin
        if (rst_x) begin
            htr_m <= 1'b0; htr_state_s <= 1'b0; sync_m <= 1'b0; sync_in_s <= 1'b0; sync_d <= 1'b0;
            h_d <= 1'b0; h_start <= 1'b0;
            tr_cnt <= 8'd0; f_sync <= 1'b0;
            htr_sync <= 1'b0;
            sync_valid <= 1'b0; sync_tick <= 64'd0; sync_count <= 16'd0;
            l_tr <= 8'd0; l_hs <= 1'b0; l_he <= 1'b0; l_sync <= 1'b0; l_first <= 1'b0; l_last <= 1'b0;
        end else begin
            htr_m       <= htr_state;
            htr_state_s <= htr_m;
            sync_m      <= sync_in;
            sync_in_s   <= sync_m;
            sync_d      <= sync_in_s;
            h_d         <= h;
            if (gate_last)
                htr_sync <= htr_req;          // heater changes only here: visible on the first tick of the next gate
            if (ld) begin
                // shadow of the gate that just ended
                l_tr    <= tr_cnt;
                l_hs    <= h_start;
                l_he    <= h_d;
                l_sync  <= f_sync;
                l_first <= first_d;
                l_last  <= last_d;
                // restart with this tick's own contribution
                h_start <= h;
                tr_cnt  <= {7'd0, h_tr};
                f_sync  <= sync_rise;
            end else begin
                tr_cnt  <= tr_cnt + {7'd0, h_tr & ~(&tr_cnt)};
                f_sync  <= f_sync | sync_rise;
            end
            if (ctrl_sync_rearm)
                sync_valid <= 1'b0;
            if (sync_rise) begin
                sync_count <= sync_count + 16'd1;
                if (!sync_valid) begin
                    sync_valid <= 1'b1;
                    sync_tick  <= {tick_hi, tick_lo};
                end
            end
        end
    end

    // ------------------------------------------------------------------ accumulator server
    // All per-gate totals live in a 2 x 64-word block RAM `acc` (address {bank, idx}):
    //   idx 4c+0, 4c+1, 4c+2  events of chain c classified 0 (beta/ref), 1 (reject), 2 (alpha)
    //   idx 4c+3              dead ticks of chain c            (live = gate ticks - dead)
    //   idx 32                heater-on ticks        idx 33    pulser pulses
    // A 24-slot round robin serves one client per tick with a 2-tick read-modify-write pipeline:
    //   slots 0..15  chain c = slot/2: even = dead-tick tally, odd = pending classification (+1)
    //   slot 16      heater tally        slot 17  pulser tally
    //   slots 18..23 record pass: read one total of the gate that ended and write it back as zero
    // A chain cannot classify twice within 26 ticks (W >= 24), so one pending slot per chain is enough;
    // a violation would set FLAGS.ACC_ERR instead of being lost silently.
    (* no_rw_check *) reg [31:0] acc [0:127];
    reg  [4:0]  slot;
    wire [9:0]  t_inc   = {pul_rise, h, ch_dead};
    wire [9:0]  t_old, t_valid;
    wire [69:0] t_amt;
    reg  [7:0]  pend, pend_bank;
    reg  [15:0] pend_cls;
    reg         acc_err;

    wire        slot_tally = (slot < 5'd16) ? ~slot[0] : (slot < 5'd18);
    wire [3:0]  tally_i    = (slot < 5'd16) ? {1'b0, slot[3:1]} : {3'b100, slot[0]};
    wire        slot_cls   = (slot < 5'd16) & slot[0];
    wire [2:0]  cls_c      = slot[3:1];
    wire        slot_ser   = (slot >= 5'd18);

    generate
        for (gi = 0; gi < 10; gi = gi + 1) begin : g_tally
            hevt_tally u_t (
                .clk(clk), .rst(rst_x), .ld(ld), .inc(t_inc[gi]),
                .serve(slot_tally && (tally_i == gi)),
                .amt(t_amt[7*gi +: 7]), .old(t_old[gi]), .valid(t_valid[gi])
            );
        end
    endgenerate

    reg  [6:0] tally_amt;
    always @(*) begin
        case (tally_i)
            4'd0:    tally_amt = t_amt[6:0];
            4'd1:    tally_amt = t_amt[13:7];
            4'd2:    tally_amt = t_amt[20:14];
            4'd3:    tally_amt = t_amt[27:21];
            4'd4:    tally_amt = t_amt[34:28];
            4'd5:    tally_amt = t_amt[41:35];
            4'd6:    tally_amt = t_amt[48:42];
            4'd7:    tally_amt = t_amt[55:49];
            4'd8:    tally_amt = t_amt[62:56];
            default: tally_amt = t_amt[69:63];
        endcase
    end
    wire [5:0] tally_idx = tally_i[3] ? {5'b10000, tally_i[0]} : {1'b0, tally_i[2:0], 2'b11};

    // record pass request (from the serialiser below)
    reg        ser_req;
    reg [5:0]  ser_idx;
    wire       ser_take = slot_ser & ser_req;

    // stage 0 -> 1: operation register
    reg        op_v, op_rc;
    reg [6:0]  op_addr, op_amt;
    // stage 1 -> 2
    reg        p1_v, p1_rc;
    reg [6:0]  p1_addr, p1_amt;
    reg [31:0] acc_q;
    reg        ser_ack;
    reg [31:0] ser_q;

    always @(posedge clk) begin
        if (rst_x) begin
            slot <= 5'd0;
            pend <= 8'd0; pend_bank <= 8'd0; pend_cls <= 16'd0;
            op_v <= 1'b0; op_rc <= 1'b0; op_addr <= 7'd0; op_amt <= 7'd0;
            p1_v <= 1'b0; p1_rc <= 1'b0; p1_addr <= 7'd0; p1_amt <= 7'd0;
            ser_ack <= 1'b0; ser_q <= 32'd0;
            acc_err <= 1'b0;
        end else begin
            slot    <= (slot == 5'd23) ? 5'd0 : slot + 5'd1;
            acc_err <= 1'b0;
            // operation select
            op_v  <= 1'b0;
            op_rc <= 1'b0;
            if (slot_tally) begin
                op_v    <= t_valid[tally_i];
                op_addr <= {bank ^ t_old[tally_i], tally_idx};
                op_amt  <= tally_amt;
            end else if (slot_cls) begin
                op_v    <= pend[cls_c];
                op_addr <= {pend_bank[cls_c], 1'b0, cls_c, pend_cls[{cls_c, 1'b0} +: 2]};
                op_amt  <= 7'd1;
            end else if (ser_take) begin
                op_v    <= 1'b1;
                op_rc   <= 1'b1;
                op_addr <= {~bank, ser_idx};
                op_amt  <= 7'd0;
            end
            // pending classifications (set wins over the clear of the same tick)
            if (slot_cls)
                pend[cls_c] <= 1'b0;
            for (k = 0; k < 8; k = k + 1) begin
                if (ch_done[k]) begin
                    pend[k]            <= 1'b1;
                    pend_bank[k]       <= bank;
                    pend_cls[2*k +: 2] <= ch_class[2*k +: 2];
                    if (pend[k] && !(slot_cls && (cls_c == k[2:0])))
                        acc_err <= 1'b1;
                end
            end
            // pipeline
            p1_v    <= op_v;
            p1_rc   <= op_rc;
            p1_addr <= op_addr;
            p1_amt  <= op_amt;
            ser_ack <= p1_v & p1_rc;
            if (ld)
                ser_q <= gate_start[63:32];      // parked here until the record pass emits START_TICK_HI
            else if (p1_v && p1_rc)
                ser_q <= acc_q;
            if (op_v && p1_v && (op_addr == p1_addr))
                acc_err <= 1'b1;             // read of an entry that is being rewritten: must never happen
        end
    end
    always @(posedge clk) begin
        acc_q <= acc[op_addr];
        if (init_run)
            acc[init_cnt] <= 32'd0;
        else if (p1_v)
            acc[p1_addr] <= p1_rc ? 32'd0 : (acc_q + {25'd0, p1_amt});
    end

    // ------------------------------------------------------------------ record pass and FIFO
    // Starts 64 ticks after `ld` (all contributions of the ended gate are in `acc` after at most 2 rounds) and runs
    // for EVERY gate, armed or not, because it also zeroes the bank for its next use. Words are produced in record
    // order; if the gate was armed and the FIFO had room they are written to `mem` and committed at the end.
    (* no_rw_check *) reg [31:0] mem [0:511];           // 8 slots x 64 words -> 4 x SB_RAM40_4K
    localparam [2:0] X_IDLE = 3'd0, X_DELAY = 3'd1, X_WORD = 3'd2, X_RAM = 3'd3, X_CALC = 3'd4, X_EMIT = 3'd5,
                     X_DONE = 3'd6;
    reg [2:0]  xs;
    reg [5:0]  x_dly;
    reg [5:0]  x_w;
    reg        x_store, x_sat, l_prev_lost, prev_lost;
    reg [31:0] x_word, x_sum;
    reg        overrun_evt, pop_empty_evt, sat_evt;

    assign ser_idle = (xs == X_IDLE);
    assign ser_done = (xs == X_DONE);

    // word decode: kind 0 = register word, 1 = class count (clamped), 2 = live (gate ticks - dead), 3 = raw total
    reg [1:0] x_kind;
    reg [5:0] x_idx;
    reg [2:0] x_chain;
    reg       x_diag;
    always @(*) begin
        x_kind  = 2'd0;
        x_idx   = 6'd0;
        x_chain = 3'd0;
        x_diag  = 1'b0;
        if (x_w == 6'd6) begin
            x_kind = 2'd3; x_idx = 6'd32;
        end else if (x_w == 6'd7) begin
            x_kind = 2'd3; x_idx = 6'd33;
        end else if (x_w >= 6'd10 && x_w < 6'd30) begin
            // floor lane L = (w - 10) / 5, k = (w - 10) % 5 : ALPHA, BETA, REJECT, LIVE, DIAG
            case (x_w)
                6'd10, 6'd11, 6'd12, 6'd13, 6'd14: x_chain = 3'd0;
                6'd15, 6'd16, 6'd17, 6'd18, 6'd19: x_chain = 3'd1;
                6'd20, 6'd21, 6'd22, 6'd23, 6'd24: x_chain = 3'd2;
                default:                           x_chain = 3'd3;
            endcase
            case (x_w)
                6'd10, 6'd15, 6'd20, 6'd25: begin x_kind = 2'd1; x_idx = {1'b0, x_chain, 2'd2}; end
                6'd11, 6'd16, 6'd21, 6'd26: begin x_kind = 2'd1; x_idx = {1'b0, x_chain, 2'd0}; end
                6'd12, 6'd17, 6'd22, 6'd27: begin x_kind = 2'd1; x_idx = {1'b0, x_chain, 2'd1}; end
                6'd13, 6'd18, 6'd23, 6'd28: begin x_kind = 2'd2; x_idx = {1'b0, x_chain, 2'd3}; end
                default:                    x_diag = 1'b1;
            endcase
        end else if (x_w >= 6'd30 && x_w < 6'd46) begin
            // reference lane L = (w - 30) / 4 (chain 4 + L), k = (w - 30) % 4 : COUNT, REJECT, LIVE, DIAG
            x_chain = (x_w < 6'd34) ? 3'd4 : (x_w < 6'd38) ? 3'd5 : (x_w < 6'd42) ? 3'd6 : 3'd7;
            case (x_w[1:0])
                2'd2:    begin x_kind = 2'd1; x_idx = {1'b0, x_chain, 2'd0}; end
                2'd3:    begin x_kind = 2'd1; x_idx = {1'b0, x_chain, 2'd1}; end
                2'd0:    begin x_kind = 2'd2; x_idx = {1'b0, x_chain, 2'd3}; end
                default: x_diag = 1'b1;
            endcase
        end
    end

    wire [31:0] rec_flags = {l_tr, fe_chain_en, 7'd0, l_last, l_sync, l_he, l_hs, (l_tr != 8'd0), l_first,
                             l_prev_lost, pul_en, st_en};
    wire [7:0]  diag_orphan = ch_sh_orphan[{x_chain, 3'd0} +: 8];
    wire [2:0]  diag_flags  = ch_sh_flags[{1'b0, x_chain, 1'b0} + {2'b00, x_chain} +: 3];
    wire [31:0] diag_word   = {16'd0, diag_orphan, 3'd0, ~fe_chain_en[x_chain], diag_flags, x_sat};
    reg  [31:0] reg_word;
    always @(*) begin
        case (x_w)
            6'd0:    reg_word = `HEVT_REC_HDR_VALUE;
            6'd1:    reg_word = seq;
            6'd4:    reg_word = {6'd0, cfg_gate_ticks};   // = length of the gate whenever it was armed (frozen)
            6'd5:    reg_word = rec_flags;
            6'd8:    reg_word = cfg_crc;
            6'd9:    reg_word = {16'd0, lost_total};
            default: reg_word = x_diag ? diag_word : 32'd0;
        endcase
    end
    wire        clamp     = (ser_q[31:CNT_W] != {(32-CNT_W){1'b0}});
    wire [31:0] cnt_clamp = clamp ? (32'd1 << CNT_W) : ser_q;
    wire [25:0] live_calc = cfg_gate_ticks - ser_q[25:0];
    wire        pop_ok    = ctrl_pop & (fifo_level != 4'd0);
    wire        mem_we    = (xs == X_EMIT) & x_store;

    always @(posedge clk) begin
        if (mem_we)
            mem[{wr_slot, x_w}] <= (x_w == REC_LAST) ? x_sum : x_word;
    end

    always @(posedge clk) begin
        overrun_evt   <= 1'b0;
        pop_empty_evt <= 1'b0;
        sat_evt       <= 1'b0;
        commit        <= 1'b0;
        if (rst_x) begin
            xs <= X_IDLE; x_dly <= 6'd0; x_w <= 6'd0; x_store <= 1'b0; x_sat <= 1'b0;
            x_word <= 32'd0; x_sum <= 32'd0;
            ser_run <= 1'b0; ser_armed <= 1'b0; ser_req <= 1'b0; ser_idx <= 6'd0;
            fifo_level <= 4'd0; rd_slot <= 3'd0; wr_slot <= 3'd0;
            lost_total <= 16'd0; prev_lost <= 1'b0; l_prev_lost <= 1'b0;
        end else begin
            case (xs)
                X_IDLE: begin
                    if (ld) begin
                        // START_TICK of the ended gate is still in gate_start on this tick only: its low word
                        // goes to x_word, its high word to ser_q, and words 2 and 3 are emitted first.
                        xs        <= X_EMIT;
                        x_dly     <= 6'd63;
                        x_w       <= 6'd2;
                        x_word    <= gate_start[31:0];
                        x_sum     <= 32'd0;
                        x_sat     <= 1'b0;
                        ser_run   <= 1'b1;
                        ser_armed <= armed_d;
                        if (armed_d && (fifo_level == FIFO_DEPTH)) begin
                            // FIFO full at the gate boundary: this gate is dropped, loudly
                            x_store     <= 1'b0;
                            overrun_evt <= 1'b1;
                            prev_lost   <= 1'b1;
                            if (lost_total != 16'hFFFF)
                                lost_total <= lost_total + 16'd1;
                        end else begin
                            x_store <= armed_d;
                            if (armed_d) begin
                                l_prev_lost <= prev_lost;
                                prev_lost   <= 1'b0;
                            end
                        end
                    end
                end
                X_DELAY: begin
                    x_dly <= x_dly - 6'd1;
                    if (x_dly == 6'd0)
                        xs <= X_WORD;
                end
                X_WORD: begin
                    if (x_kind == 2'd0) begin
                        x_word <= reg_word;
                        xs     <= X_EMIT;
                    end else begin
                        ser_req <= 1'b1;
                        ser_idx <= x_idx;
                        xs      <= X_RAM;
                    end
                end
                X_RAM: begin
                    if (ser_take)
                        ser_req <= 1'b0;
                    if (ser_ack)
                        xs <= X_CALC;
                end
                X_CALC: begin
                    case (x_kind)
                        2'd1: begin
                            x_word <= cnt_clamp;
                            if (clamp) begin
                                x_sat   <= 1'b1;
                                sat_evt <= 1'b1;
                            end
                        end
                        2'd2:    x_word <= {6'd0, live_calc};
                        default: x_word <= ser_q;
                    endcase
                    xs <= X_EMIT;
                end
                X_EMIT: begin
                    x_sum <= x_sum + x_word;
                    if (x_diag)
                        x_sat <= 1'b0;
                    // word order: 2, 3, (wait), 0, 1, 4, 5, ... 47
                    if (x_w == REC_LAST)
                        xs <= X_DONE;
                    else if (x_w == 6'd2) begin
                        x_w    <= 6'd3;
                        x_word <= ser_q;
                    end else if (x_w == 6'd3) begin
                        x_w <= 6'd0;
                        xs  <= X_DELAY;
                    end else begin
                        x_w <= (x_w == 6'd1) ? 6'd4 : x_w + 6'd1;
                        xs  <= X_WORD;
                    end
                end
                X_DONE: begin
                    commit  <= x_store;
                    ser_run <= 1'b0;
                    xs      <= X_IDLE;
                end
                default: xs <= X_IDLE;
            endcase
            // FIFO pointers
            if (commit)
                wr_slot <= wr_slot + 3'd1;
            if (ctrl_flush) begin
                fifo_level <= 4'd0;
                rd_slot    <= wr_slot + {2'd0, commit};
                lost_total <= 16'd0;
                prev_lost  <= 1'b0;
            end else begin
                if (pop_ok)
                    rd_slot <= rd_slot + 3'd1;
                fifo_level <= fifo_level + {3'd0, commit} - {3'd0, pop_ok};
                if (ctrl_pop && !pop_ok)
                    pop_empty_evt <= 1'b1;
            end
        end
    end

    // ------------------------------------------------------------------ trigger
    wire [7:0] trig_hit;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_trig
            wire [1:0] c = ch_class[2*gi +: 2];
            wire cls_en = (gi < 4) ?
                ((c == 2'd0) & trig_cfg[`HEVT_TRIG_CFG_BETA_B]) | ((c == 2'd1) & trig_cfg[`HEVT_TRIG_CFG_REJECT_B]) |
                ((c == 2'd2) & trig_cfg[`HEVT_TRIG_CFG_ALPHA_B]) :
                ((c == 2'd0) & trig_cfg[`HEVT_TRIG_CFG_REF_B]) | ((c == 2'd1) & trig_cfg[`HEVT_TRIG_CFG_REF_REJECT_B]);
            assign trig_hit[gi] = trig_cfg[gi] &
                ((trig_cfg[`HEVT_TRIG_CFG_START_B] & ch_start[gi]) | (ch_done[gi] & cls_en));
        end
    endgenerate
    wire trig_pul = trig_cfg[`HEVT_TRIG_CFG_PULSER_B] & pul_rise;
    wire trig_req = (|trig_hit) | trig_pul;

    reg [2:0] hit_idx;
    always @(*) begin
        hit_idx = 3'd0;
        for (k = 7; k >= 0; k = k - 1)
            if (trig_hit[k])
                hit_idx = k[2:0];
    end
    wire [1:0] hit_class = ch_class[{hit_idx, 1'b0} +: 2];
    wire       hit_done  = ch_done[hit_idx];

    reg [7:0] trig_w;
    wire [7:0] trig_w_eff = (trig_cfg[`HEVT_TRIG_CFG_WIDTH_R] == 8'd0) ? 8'd1 : trig_cfg[`HEVT_TRIG_CFG_WIDTH_R];
    always @(posedge clk) begin
        if (rst_x) begin
            trig_out <= 1'b0; trig_w <= 8'd0;
            trig_fired <= 1'b0; trig_chain <= 3'd0; trig_src <= 3'd0; trig_tick <= 32'd0;
        end else begin
            if (trig_out) begin
                if (trig_w == 8'd0)
                    trig_out <= 1'b0;
                else
                    trig_w <= trig_w - 8'd1;
            end
            if (ctrl_trig_rearm)
                trig_fired <= 1'b0;
            if (trig_req && !ctrl_trig_rearm) begin
                if (!trig_fired) begin
                    trig_fired <= 1'b1;
                    trig_chain <= (|trig_hit) ? hit_idx : 3'd0;
                    trig_src   <= (|trig_hit) ? (hit_done ? {1'b0, hit_class} : 3'd3) : 3'd4;
                    trig_tick  <= tick_lo;
                end
                if (!trig_out && !(trig_cfg[`HEVT_TRIG_CFG_ONESHOT_B] && trig_fired)) begin
                    trig_out <= 1'b1;
                    trig_w   <= trig_w_eff - 8'd1;
                end
            end
        end
    end

    // ------------------------------------------------------------------ sticky flags, IRQ, LED
    wire [9:0] flag_set = {acc_err, sync_rise & sync_valid, pop_empty_evt, spi_frame_err, |ch_orphan, sat_evt, |ch_stuck,
                           cfg_bad, cfg_rej | ctrl_rej, overrun_evt};
    wire wr_flags = spi_wr_stb && (spi_wr_addr == `HEVT_A_FLAGS);
    wire rec_avail = (fifo_level != 4'd0);
    wire fifo_full = (fifo_level == FIFO_DEPTH);
    always @(posedge clk) begin
        if (rst_i) begin
            flags <= 10'd0;
            irq   <= 1'b0;
            led   <= 1'b0;
        end else begin
            flags <= (flags & ~(wr_flags ? wd[9:0] : 10'd0)) | flag_set;
            irq   <= (irq_en[0] & rec_avail) | (irq_en[1] & fifo_full) | (irq_en[2] & (|flags));
            case (led_mode)
                2'd0:    led <= 1'b0;
                2'd1:    led <= armed ? gate_sync : tick_lo[25];
                2'd2:    led <= armed;
                default: led <= |flags;
            endcase
        end
    end

    assign status_byte = {rec_avail, fifo_full, flags[0], armed, |flags[9:1], 3'b101};

    // ------------------------------------------------------------------ read path
    reg        rec_ok_txn;
    always @(posedge clk) begin
        if (rst_i) begin
            snap_tick  <= 64'd0;
            rec_ok_txn <= 1'b0;
        end else if (spi_cs_fall) begin
            snap_tick  <= {tick_hi, tick_lo};
            rec_ok_txn <= rec_avail;
        end
    end

    wire [31:0] status_w = {ch_busy, ch_stuck, trig_fired, sync_valid, htr_sync, htr_state_s, fifo_level,
                            st_en, pul_active, crc_valid, fifo_full, rec_avail, disarm_pending, arm_pending, armed};
    reg [31:0] reg_mux;
    always @(*) begin
        reg_mux = 32'd0;
        if (spi_addr >= `HEVT_CFG_FIRST && spi_addr < (`HEVT_CFG_FIRST + `HEVT_CFG_COUNT)) begin
            reg_mux = cfg_word;
        end else begin
            case (spi_addr)
                `HEVT_A_ID:           reg_mux = `HEVT_RST_ID;
                `HEVT_A_VERSION:      reg_mux = `HEVT_RST_VERSION;
                `HEVT_A_BUILD_ID:     reg_mux = `HEVT_BUILD_ID;
                `HEVT_A_TICK_HZ:      reg_mux = `HEVT_TICK_HZ;
                `HEVT_A_CAPS:         reg_mux = `HEVT_RST_CAPS;
                `HEVT_A_STATUS:       reg_mux = status_w;
                `HEVT_A_FLAGS:        reg_mux = {22'd0, flags};
                `HEVT_A_IRQ_EN:       reg_mux = {29'd0, irq_en};
                `HEVT_A_TICK_LO:      reg_mux = snap_tick[31:0];
                `HEVT_A_TICK_HI:      reg_mux = snap_tick[63:32];
                `HEVT_A_FIFO_STAT:    reg_mux = {lost_total, 12'd0, fifo_level};
                `HEVT_A_GATE_SEQ:     reg_mux = seq;
                `HEVT_A_CFG_CRC:      reg_mux = cfg_crc;
                `HEVT_A_GATE_POS:     reg_mux = {6'd0, gpos};
                `HEVT_A_SCRATCH:      reg_mux = scratch;
                `HEVT_A_TRIG_CFG:     reg_mux = {8'd0, trig_cfg};
                `HEVT_A_TRIG_STAT:    reg_mux = {21'd0, trig_src, 1'b0, trig_chain, 3'd0, trig_fired};
                `HEVT_A_TRIG_TICK:    reg_mux = trig_tick;
                `HEVT_A_HTR_CTRL:     reg_mux = {31'd0, htr_req};
                `HEVT_A_SYNC_TICK_LO: reg_mux = sync_tick[31:0];
                `HEVT_A_SYNC_TICK_HI: reg_mux = sync_tick[63:32];
                `HEVT_A_SYNC_STAT:    reg_mux = {8'd0, sync_count, 7'd0, sync_valid};
                `HEVT_A_LED_CFG:      reg_mux = {30'd0, led_mode};
                `HEVT_A_IN_LEVELS:    reg_mux = {10'd0, sync_in_s, htr_state_s, fe_q};
                default:              reg_mux = 32'd0;
            endcase
        end
    end

    reg [31:0] reg_q, bram_q;
    reg        rd_rec;
    always @(posedge clk) begin
        if (spi_rd_req) begin
            reg_q  <= reg_mux;
            bram_q <= mem[{rd_slot, spi_addr[5:0]}];
            rd_rec <= spi_addr[6] & rec_ok_txn & (spi_addr[5:0] <= REC_LAST);
        end
    end
    assign rd_data = rd_rec ? bram_q : reg_q;
endmodule
`default_nettype wire

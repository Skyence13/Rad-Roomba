// Rad Roomba head event logic - top level for iCE40UP5K-SG48
// 24 MHz TCXO -> SB_PLL40_PAD x2 -> 48 MHz tick clock on a global net. Power-on reset: all flip-flops of the
// iCE40 start at 0 after configuration; `rst` is held for 16 ticks after the PLL reports lock.
`default_nettype none
module head_evt_top (
    input  wire       clk_24m,
    input  wire       spi_sck,
    input  wire       spi_cs_n,
    input  wire       spi_mosi,
    output wire       spi_miso,
    output wire       irq,
    output wire       trig_out,
    output wire       pulser,
    output wire       gate_sync,
    output wire       htr_sync,
    input  wire       htr_state,
    input  wire       sync_in,
    output wire       led_n,
    input  wire [3:0] beta_lld,
    input  wire [3:0] beta_uld,
    input  wire [3:0] alpha,
    input  wire [3:0] ref_lld,
    input  wire [3:0] ref_uld
);
    wire clk;
    wire pll_lock;

    // icepll -i 24 -o 48: F_PFD 24 MHz, F_VCO 768 MHz, F_OUT 48.000 MHz
    SB_PLL40_PAD #(
        .FEEDBACK_PATH("SIMPLE"),
        .DIVR(4'b0000),
        .DIVF(7'b0011111),
        .DIVQ(3'b100),
        .FILTER_RANGE(3'b010)
    ) u_pll (
        .PACKAGEPIN(clk_24m),
        .PLLOUTGLOBAL(clk),
        .LOCK(pll_lock),
        .RESETB(1'b1),
        .BYPASS(1'b0)
    );

    reg [1:0] lock_s = 2'b00;
    reg [4:0] por    = 5'd0;
    always @(posedge clk) begin
        lock_s <= {lock_s[0], pll_lock};
        if (!lock_s[1])
            por <= 5'd0;
        else if (!por[4])
            por <= por + 5'd1;
    end
    wire rst = ~por[4];

    wire miso_i, led;
    hevt_core u_core (
        .clk(clk), .rst(rst),
        .beta_lld(beta_lld), .beta_uld(beta_uld), .alpha(alpha), .ref_lld(ref_lld), .ref_uld(ref_uld),
        .spi_sck(spi_sck), .spi_cs_n(spi_cs_n), .spi_mosi(spi_mosi), .spi_miso(miso_i),
        .htr_state(htr_state), .sync_in(sync_in),
        .irq(irq), .trig_out(trig_out), .pulser(pulser), .gate_sync(gate_sync), .htr_sync(htr_sync), .led(led)
    );

    // MISO is driven only while the MCU selects the FPGA
    assign spi_miso = spi_cs_n ? 1'bz : miso_i;
    // RGB0 is an open-drain pin: low = LED on
    assign led_n = ~led;
endmodule
`default_nettype wire

// Rad Roomba head event logic - SPI slave (mode 0, MSB first), oversampled in the system clock domain
//
// Clock-domain crossing: SCK, CS_N and MOSI are asynchronous to clk. Each goes through a two-flip-flop
// synchroniser; edges are then detected on a third stage. Nothing is clocked by SCK, so the only CDC objects are
// single-bit synchronisers. MOSI is sampled at the detected SCK rising edge through an equal-length path, i.e.
// 2..3 ticks after the pin edge, where the master holds it stable (requires SCK high >= 5 ticks).
// MISO changes 2..3 ticks (+ clock-to-pad) after the SCK falling edge at the pin; the master samples it on the
// next rising edge (requires SCK low >= 5 ticks). Limits: SCK <= 4 MHz, CS set-up and CS high >= 200 ns.
//
// Protocol (see regmap.yaml):
//   byte 0  MOSI {W, A[6:0]}                       MISO status byte (sampled at CS falling)
//   read:   byte 1 MOSI dummy                      MISO echo of byte 0
//           bytes 2.. data, 32-bit words, LSB byte first, address auto-increment (mod 128)
//   write:  bytes 1.. data, 32-bit words, LSB byte first; a word is written when its 4th byte is complete
// Read data: rd_req pulses (with rd_addr valid) at the end of the byte that precedes each word; rd_data must be
// valid 3 ticks later and stay stable.
`default_nettype none
module hevt_spi (
    input  wire        clk,
    input  wire        rst,
    input  wire        sck,
    input  wire        cs_n,
    input  wire        mosi,
    output wire        miso,
    input  wire [7:0]  status_byte,   // live; sampled at CS falling
    output reg         cs_fall,       // 1 tick: transaction start (snapshot strobe)
    output reg         rd_req,
    output reg  [6:0]  addr,
    input  wire [31:0] rd_data,
    output reg         wr_stb,
    output reg  [6:0]  wr_addr,
    output wire [31:0] wr_data,      // valid with wr_stb and for at least 8 SCK periods after it
    output reg         frame_err
);
    reg [2:0] sck_s;
    reg [2:0] cs_s;
    reg [1:0] mosi_s;

    always @(posedge clk) begin
        if (rst) begin
            sck_s  <= 3'b000;
            cs_s   <= 3'b111;
            mosi_s <= 2'b00;
        end else begin
            sck_s  <= {sck_s[1:0], sck};
            cs_s   <= {cs_s[1:0], cs_n};
            mosi_s <= {mosi_s[0], mosi};
        end
    end

    wire sck_rise  = (sck_s[2:1] == 2'b01);
    wire sck_fall  = (sck_s[2:1] == 2'b10);
    wire cs_fall_w = (cs_s[2:1] == 2'b10);
    wire cs_rise_w = (cs_s[2:1] == 2'b01);
    wire mosi_i    = mosi_s[1];

    localparam [1:0] P_CMD = 2'd0, P_ECHO = 2'd1, P_DATA = 2'd2;

    reg        active;
    reg [1:0]  phase;
    reg        is_write;
    reg [2:0]  bitc;
    reg [6:0]  sr_in;
    reg [1:0]  bidx;        // byte within the 32-bit word
    reg [31:0] wsh;
    reg [7:0]  so;
    reg [7:0]  cmd_echo;
    reg        byte_start;  // next falling edge starts a new MISO byte

    wire [7:0] rx = {sr_in, mosi_i};

    assign miso    = so[7];
    assign wr_data = wsh;

    always @(posedge clk) begin
        if (rst) begin
            active     <= 1'b0;
            phase      <= P_CMD;
            is_write   <= 1'b0;
            bitc       <= 3'd0;
            sr_in      <= 7'd0;
            bidx       <= 2'd0;
            wsh        <= 32'd0;
            so         <= 8'd0;
            cmd_echo   <= 8'd0;
            byte_start <= 1'b0;
            cs_fall    <= 1'b0;
            rd_req     <= 1'b0;
            addr       <= 7'd0;
            wr_stb     <= 1'b0;
            wr_addr    <= 7'd0;
            frame_err  <= 1'b0;
        end else begin
            cs_fall   <= 1'b0;
            rd_req    <= 1'b0;
            wr_stb    <= 1'b0;
            frame_err <= 1'b0;

            if (cs_fall_w) begin
                active     <= 1'b1;
                phase      <= P_CMD;
                bitc       <= 3'd0;
                bidx       <= 2'd0;
                is_write   <= 1'b0;
                byte_start <= 1'b0;
                so         <= status_byte;
                cs_fall    <= 1'b1;
            end else if (cs_rise_w) begin
                active <= 1'b0;
                so     <= 8'd0;
                if (active && ((bitc != 3'd0) || (is_write && (phase == P_DATA) && (bidx != 2'd0))))
                    frame_err <= 1'b1;
            end else if (active) begin
                if (sck_rise) begin
                    sr_in <= rx[6:0];
                    bitc  <= bitc + 3'd1;
                    if (bitc == 3'd7) begin
                        byte_start <= 1'b1;
                        case (phase)
                            P_CMD: begin
                                is_write <= rx[7];
                                addr     <= rx[6:0];
                                cmd_echo <= rx;
                                bidx     <= 2'd0;
                                phase    <= rx[7] ? P_DATA : P_ECHO;
                            end
                            P_ECHO: begin
                                phase  <= P_DATA;
                                rd_req <= 1'b1;          // first word
                            end
                            default: begin
                                bidx <= bidx + 2'd1;
                                if (is_write) begin
                                    wsh <= {rx, wsh[31:8]};
                                    if (bidx == 2'd3) begin
                                        wr_stb  <= 1'b1;
                                        wr_addr <= addr;
                                        addr    <= addr + 7'd1;
                                    end
                                end else if (bidx == 2'd3) begin
                                    addr   <= addr + 7'd1;
                                    rd_req <= 1'b1;      // next word
                                end
                            end
                        endcase
                    end
                end else if (sck_fall) begin
                    if (byte_start) begin
                        byte_start <= 1'b0;
                        if (phase == P_ECHO)
                            so <= cmd_echo;
                        else if (phase == P_DATA && !is_write)
                            so <= rd_data[8*bidx +: 8];
                        else
                            so <= 8'd0;
                    end else begin
                        so <= {so[6:0], 1'b0};
                    end
                end
            end
        end
    end
endmodule
`default_nettype wire

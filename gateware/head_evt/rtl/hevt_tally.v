// Rad Roomba head event logic - tick tally client of the accumulator server
//
// Counts the ticks on which `inc` is 1 in a small counter that the accumulator server empties ("serves") at
// least every 24 ticks and adds to a 32-bit total in block RAM. Gate exactness:
//   `ld` is the first tick of a gate. On that tick the counter content (ticks of the gate that just ended, not
//   yet served) moves to `resid` and the counter restarts with this tick's own inc. The next service posts
//   `resid` to the OLD gate's bank (old = 1); later services post the counter to the current bank. A service
//   that falls on the `ld` tick itself is a no-op (valid = 0). So every tick is added to exactly one gate.
`default_nettype none
module hevt_tally (
    input  wire       clk,
    input  wire       rst,
    input  wire       ld,
    input  wire       inc,
    input  wire       serve,     // the server takes amt on this tick
    output wire [6:0] amt,
    output wire       old,       // amt belongs to the gate that ended
    output wire       valid
);
    reg [6:0] cnt, resid;
    reg       resid_v;

    assign old   = resid_v;
    assign amt   = resid_v ? resid : cnt;
    assign valid = ~ld;

    always @(posedge clk) begin
        if (rst) begin
            cnt     <= 7'd0;
            resid   <= 7'd0;
            resid_v <= 1'b0;
        end else if (ld) begin
            resid   <= cnt;
            resid_v <= 1'b1;
            cnt     <= {6'd0, inc};
        end else begin
            if (serve && resid_v)
                resid_v <= 1'b0;
            if (serve && !resid_v)
                cnt <= {6'd0, inc};
            else
                cnt <= cnt + {6'd0, inc};
        end
    end
endmodule
`default_nettype wire

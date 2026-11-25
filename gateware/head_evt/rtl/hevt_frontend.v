// Rad Roomba head event logic - comparator input front end (one instance per comparator input)
//
// Metastability / pulse-capture treatment
//   d_async is an asynchronous, active-high comparator output (or, in self-test, a registered synthetic signal).
//   1. Pulse catcher: a flip-flop with ASYNCHRONOUS SET driven by d_async. Any high level on d_async that is long
//      enough to set a flip-flop through its set input is remembered, however it falls relative to the clock.
//      The catcher is cleared synchronously once the captured '1' has reached the second synchroniser stage, and
//      only if d_async is low at that clock edge (set dominates), so a long input keeps q high for its whole length.
//   2. Two-flip-flop synchroniser (m1, m2) on the catcher output. The catcher can go metastable when d_async falls
//      (set removal) or rises next to a clock edge while it is being cleared; m1 gives it one full 20.8 ns tick to
//      resolve before m2 samples it. All downstream logic uses m2 only.
//   Result seen by the event logic (q):
//      a pulse of any captured width gives q high for at least 3 ticks;
//      a rising edge at the pin between clock edges e-1 and e is seen as q = 1 from the tick that follows edge e+1
//      (latency 1..2 tick periods from the pin edge to the launching clock edge, i.e. q rises 2 edges after it);
//      a level longer than 2 ticks gives q high for (its length rounded to ticks) + 2..3 ticks.
//   SYNC_ONLY = 1 bypasses the catcher: plain two-flip-flop synchroniser, pulses shorter than one tick period plus
//   set-up/hold can be missed (diagnostic mode; lets the benefit of the catcher be measured on hardware).
//
// Minimum pulse width: in RTL simulation the catcher captures any non-zero width. On silicon the limit is the
// minimum set pulse width of the iCE40UP logic-cell flip-flop plus pad/routing pulse shrinkage; it is NOT
// characterised by the open tools. Requirement placed on the analog design: >= 5 ns at the FPGA pin, to be
// confirmed with a pulser on hardware (README, "Hardware re-verification").
`default_nettype none
module hevt_frontend (
    input  wire clk,
    input  wire rst,
    input  wire d_async,     // asynchronous input (post self-test mux)
    input  wire sync_only,   // 1 = bypass pulse catcher
    output wire q            // synchronised, stretched level
);
    reg caught;
    reg m1;
    reg m2;

    // pulse catcher: asynchronous set, synchronous clear (maps to SB_DFFES)
    always @(posedge clk or posedge d_async) begin
        if (d_async)
            caught <= 1'b1;
        else if (rst || m2)
            caught <= 1'b0;
    end

    wire src = sync_only ? d_async : caught;

    always @(posedge clk) begin
        if (rst) begin
            m1 <= 1'b0;
            m2 <= 1'b0;
        end else begin
            m1 <= src;
            m2 <= m1;
        end
    end

    assign q = m2;
endmodule
`default_nettype wire

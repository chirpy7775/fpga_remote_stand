// GPIO → LED test for Terasic DE10-Lite (MAX 10 10M50DAF484C7G).
// Raspberry Pi drives 8 lines; FPGA only *reads* them (safe: no output fight).
//
// LEDR[0..7] = pins 1..8
// LEDR[8]    = all eight high
// LEDR[9]    = heartbeat (~0.75 Hz) so you know the bitstream is alive

module gpio_led_test (
    input  wire       clk_50,
    input  wire [7:0] gpio_in,
    output wire [9:0] ledr
);

    reg [25:0] div;

    always @(posedge clk_50)
        div <= div + 1'b1;

    assign ledr[7:0] = gpio_in;
    assign ledr[8]   = &gpio_in;
    assign ledr[9]   = div[25];

endmodule

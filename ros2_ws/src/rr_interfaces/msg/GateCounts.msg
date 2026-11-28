# One ACQ 2.0 gate joined to its host attachment (head ICD section 5).
std_msgs/Header header            # stamp = gate start converted to ROS time
string attachment_session_id      # host-generated UUID of the bound attachment
uint64 sequence
uint64 start_us                   # head clock
uint32 span_us
int64 host_t0_us                  # host monotonic clock (CLOCK_MONOTONIC), -1 when no fit
int64 host_t1_us
float64 time_bound_us             # host clock-fit bound over the gate, <0 when unavailable
string fit_id
string sync_state
float32 head_c
string[] flags
rr_interfaces/LaneCounts[4] lanes

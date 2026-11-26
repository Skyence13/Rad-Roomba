std_msgs/Header header
bool hw_latch
bool traction_inhibited
bool charge_service
string[] hw_inhibit_reasons       # contract enums.hw_inhibit_reason (latched)
string[] protective_stop_reasons  # contract enums.protective_stop_reason (latched)
string[] hold
string[] chain_open               # safety_chain ids currently open
bool rearm_ready

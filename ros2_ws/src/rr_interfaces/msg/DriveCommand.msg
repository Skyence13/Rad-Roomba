# Bounded velocity request to the chassis bridge. Never queued: the bridge keeps only the
# newest command and drops it when older than its validity.
std_msgs/Header header
float32 v_mps
float32 w_radps
string source

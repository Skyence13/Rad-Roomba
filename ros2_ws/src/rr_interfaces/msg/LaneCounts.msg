# One lane of one gate. A null channel on the wire is has_*=false (never a zero).
uint8 lane
bool has_alpha
uint32 alpha_counts
bool has_beta
uint32 beta_counts
uint32 floor_live_us
bool has_ref
uint32 ref_counts
uint32 ref_live_us
string[] flags
bool eligible            # instrument + host timing eligible (pose qualification is separate)
string[] reasons

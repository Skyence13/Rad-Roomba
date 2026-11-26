# Immutable record written at BIND, before the first frame (head ICD section 4).
std_msgs/Header header
string attachment_session_id
string head_id
string head_type
string boot_id
string firmware
string setup_id
string descriptor_id
string descriptor_sha256
string geometry_id
string geometry_basis
string calibration_id
string mode
bool field_use_approved
string manifest_json              # complete manifest incl. mount transform (descriptor bytes omitted)

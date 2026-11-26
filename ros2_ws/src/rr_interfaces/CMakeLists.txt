cmake_minimum_required(VERSION 3.8)
project(rr_interfaces)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(action_msgs REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/LaneCounts.msg" "msg/GateCounts.msg" "msg/AttachmentManifest.msg" "msg/SessionEvent.msg"
  "msg/ChassisState.msg" "msg/SafetyState.msg" "msg/DriveCommand.msg" "msg/LocalizationStatus.msg"
  "msg/CoverageStatus.msg" "msg/Flag.msg" "msg/FlagArray.msg" "msg/MissionState.msg"
  "srv/MissionCommand.srv" "srv/ExportSurvey.srv" "action/GuidedVisit.action"
  DEPENDENCIES std_msgs action_msgs)
ament_export_dependencies(rosidl_default_runtime)
ament_package()

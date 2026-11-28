# Rad Roomba robot-software build/test/run image.
#
# Base: the official ROS 2 Jazzy "ros-base" image, pinned by digest (the tag
# is kept for readability; the digest is what is pulled).
# Extra packages: Ubuntu 24.04 archive only (no PyPI, no packages.ros.org).
# The resolved versions are written to /opt/rr/versions.lock at build time and
# compared with ros2_ws/docker/versions.lock by tools/build.sh.
#
# No Nav2 (DEC-030), no Gazebo.
ARG BASE=ros:jazzy-ros-base@sha256:5147d3ae250ce754afd399f6bfec15b33dd4e473ca357e30432a3182031bfad6
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    LC_ALL=C.UTF-8

# packages.ros.org is not reachable from the project build network. Every ROS
# package this workspace needs is already inside the base image, so the ROS
# apt source is removed to let `apt-get update` succeed against the Ubuntu
# archive alone. (Nothing is bypassed: no ROS package is installed here.)
RUN rm -f /etc/apt/sources.list.d/ros2.sources /etc/apt/sources.list.d/ros2*.list

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3-numpy \
      python3-yaml \
      python3-pytest \
      python3-shapely \
      python3-aiohttp \
      python3-serial \
      python3-jsonschema \
      python3-scipy \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/rr \
 && dpkg-query -W -f='${Package}=${Version}\n' \
      python3-numpy python3-yaml python3-pytest python3-shapely \
      python3-aiohttp python3-serial python3-jsonschema python3-scipy \
      ros-jazzy-rclpy ros-jazzy-launch-ros ros-jazzy-rosidl-default-generators \
      ros-jazzy-sensor-msgs ros-jazzy-nav-msgs ros-jazzy-tf2-ros \
      python3-colcon-core > /opt/rr/versions.lock

WORKDIR /ws

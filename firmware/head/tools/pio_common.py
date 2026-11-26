# PlatformIO pre-script: compile firmware/common (outside the project directory) into the image.
Import("env")  # noqa: F821  (provided by PlatformIO/SCons)

env.BuildSources("$BUILD_DIR/rr_common", "$PROJECT_DIR/../common/src")  # noqa: F821

# PlatformIO extra script: use the Cortex-M4F hardware FPU (single precision) for compile AND link.
# The chassis core does its control arithmetic in float inside the 1 kHz interrupt.
Import("env")  # noqa: F821

flags = ["-mfloat-abi=hard", "-mfpu=fpv4-sp-d16"]
env.Append(CCFLAGS=flags, LINKFLAGS=flags, ASFLAGS=flags)  # noqa: F821

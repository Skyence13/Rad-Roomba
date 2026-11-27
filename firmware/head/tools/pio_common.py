# PlatformIO pre-script: compile firmware/common (outside the project directory) into the image.
Import("env")  # noqa: F821  (provided by PlatformIO/SCons)

import subprocess

try:  # build identity: git commit of the checkout (read-only), "-dirty" if the tree has changes
    commit = subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], cwd=env.subst("$PROJECT_DIR"), text=True).strip()  # noqa: F821
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "."], cwd=env.subst("$PROJECT_DIR"), text=True).strip()  # noqa: F821
    env.Append(CPPDEFINES=[("RRH_BUILD_ID", '\\"%s%s\\"' % (commit, "-dirty" if dirty else ""))])  # noqa: F821
except Exception:  # noqa: BLE001
    pass  # RRH_BUILD_ID stays "unversioned"

env.BuildSources("$BUILD_DIR/rr_common", "$PROJECT_DIR/../common/src")  # noqa: F821

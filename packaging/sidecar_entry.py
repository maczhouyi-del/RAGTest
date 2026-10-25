"""Frozen entry, including the fixed stdlib resource-tracker helper used by Torch."""

import re
import sys
from subprocess import _args_from_interpreter_flags


def resource_tracker_fd(arguments, interpreter_flags):
    # PyInstaller's generic freeze_support executes a prefix-matched -c string.
    # This application accepts only the exact stdlib tracker and calls it directly.
    if arguments[:-2] != interpreter_flags or len(arguments) < 2 or arguments[-2] != "-c":
        return None
    match = re.fullmatch(
        r"from multiprocessing\.resource_tracker import main;main\(([0-9]{1,10})\)", arguments[-1]
    )
    if match and 3 <= int(match[1]) <= 2147483647:
        return int(match[1])
    return None


if __name__ == "__main__":
    fd = resource_tracker_fd(sys.argv[1:], _args_from_interpreter_flags())
    if fd is not None:
        from multiprocessing.resource_tracker import main as tracker_main

        tracker_main(fd)
        raise SystemExit(0)
    from ragsystem.__main__ import main

    raise SystemExit(main())

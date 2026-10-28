"""Irreversible Linux filesystem + syscall confinement, applied before parsing untrusted bytes."""

import errno
import sys
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    pass


def confine(input_path, required=False):
    if not sys.platform.startswith("linux"):
        if required:
            raise SandboxUnavailable(
                "Kernel document isolation requires the validated Linux deployment."
            )
        return {"mode": "development_rlimits_only", "network_filesystem_isolated": False}
    try:
        import landlockpy
        import pyseccomp as seccomp

        abi = landlockpy.abi_version()
        if abi < 1:
            raise SandboxUnavailable("Landlock unavailable.")
    except (ImportError, OSError, SandboxUnavailable):
        if required:
            raise SandboxUnavailable("Required kernel document isolation is unavailable.") from None
        return {"mode": "development_rlimits_only", "network_filesystem_isolated": False}
    filt = seccomp.SyscallFilter(defaction=seccomp.ALLOW)
    blocked = (
        "socket",
        "socketpair",
        "connect",
        "bind",
        "listen",
        "accept",
        "accept4",
        "socketcall",
        "sendto",
        "sendmsg",
        "sendmmsg",
        "recvfrom",
        "recvmsg",
        "recvmmsg",
        "ptrace",
        "process_vm_readv",
        "process_vm_writev",
        "pidfd_getfd",
        "pidfd_send_signal",
        "kill",
        "tkill",
        "tgkill",
        "bpf",
        "perf_event_open",
        "userfaultfd",
        "mount",
        "umount2",
        "pivot_root",
        "unshare",
        "setns",
        "clone",
        "clone3",
        "fork",
        "vfork",
        "execve",
        "execveat",
        "open_by_handle_at",
        "name_to_handle_at",
        "io_uring_setup",
        "io_uring_enter",
        "io_uring_register",
    )
    for name in blocked:
        if seccomp.resolve_syscall(seccomp.Arch.NATIVE, name) >= 0:
            filt.add_rule(seccomp.ERRNO(errno.EPERM), name)
    from landlockpy import AccessFS, AccessNet, Ruleset, fs_for_abi, scope_for_abi

    read = AccessFS.READ_FILE | AccessFS.READ_DIR
    with Ruleset(
        handled_fs=fs_for_abi(abi),
        handled_net=AccessNet.NONE,
        scoped=scope_for_abi(abi),
        best_effort=False,
    ) as rules:
        # Dependency/standard-library reads only, not /app, /run/secrets, /home or /proc.
        for root in {
            Path(sys.prefix).resolve(),
            Path(sys.base_prefix).resolve(),
            Path("/usr/lib"),
            Path("/usr/local/lib"),
            Path("/lib").resolve(),
        }:
            if root.is_dir():
                rules.allow_path(root, read)
        rules.allow_path(Path(input_path).resolve(), AccessFS.READ_FILE)
        if Path("/dev/urandom").exists():
            rules.allow_path("/dev/urandom", AccessFS.READ_FILE)
        rules.restrict()
    filt.load()
    return {
        "mode": "linux_landlock_seccomp",
        "landlock_abi": abi,
        "network_filesystem_isolated": True,
        "child_execution_denied": True,
        "filesystem_writes_denied": True,
    }

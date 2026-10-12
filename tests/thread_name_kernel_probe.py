"""Native test program for T1 kernel feasibility, not producer admission."""

KERNEL_CODE = r"""
import array, ctypes, errno, fcntl, json, os, signal, socket, struct, threading, tempfile, select

signal.alarm(30)
SYS_SECCOMP = 317
SYS_OPENAT = 257
SYS_UNSHARE = 272
AT_FDCWD = -100
CLONE_NEWUSER = 0x10000000
SECCOMP_SET_MODE_FILTER = 1
SECCOMP_FILTER_FLAG_NEW_LISTENER = 8
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_USER_NOTIF = 0x7FC00000
AUDIT_ARCH_X86_64 = 0xC000003E
O_WRONLY = 1
O_CREAT = 64
O_TRUNC = 512
O_CLOEXEC = 0o2000000
O_NOFOLLOW = 0o400000
EXPECTED_FLAGS = O_WRONLY | O_CREAT | O_TRUNC
IOC_NRBITS = 8
IOC_TYPEBITS = 8
IOC_SIZEBITS = 14
IOC_NRSHIFT = 0
IOC_TYPESHIFT = 8
IOC_SIZESHIFT = 16
IOC_DIRSHIFT = 30
IOC_WRITE = 1
IOC_READ = 2


def ioc(direction, number, size):
    return (
        (direction << IOC_DIRSHIFT)
        | (ord("!") << IOC_TYPESHIFT)
        | (number << IOC_NRSHIFT)
        | (size << IOC_SIZESHIFT)
    )


NOTIF_RECV = ioc(IOC_READ | IOC_WRITE, 0, 80)
NOTIF_ID_VALID = ioc(IOC_WRITE, 2, 8)
NOTIF_ADDFD = ioc(IOC_WRITE, 3, 24)
ADDFD_FLAG_SEND = 2


class Filter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    ]


class Program(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]


class Iovec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("length", ctypes.c_size_t)]


class CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class CapData(ctypes.Structure):
    _fields_ = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


class Ruleset(ctypes.Structure):
    _fields_ = [("fs", ctypes.c_uint64), ("net", ctypes.c_uint64), ("scope", ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("access", ctypes.c_uint64), ("fd", ctypes.c_int)]


native = ctypes.CDLL(None, use_errno=True)
native.syscall.restype = ctypes.c_long
native.process_vm_readv.argtypes = [
    ctypes.c_int,
    ctypes.POINTER(Iovec),
    ctypes.c_ulong,
    ctypes.POINTER(Iovec),
    ctypes.c_ulong,
    ctypes.c_ulong,
]
native.process_vm_readv.restype = ctypes.c_ssize_t


def raise_errno(name):
    raise OSError(ctypes.get_errno(), name)


def vmread(pid, address):
    out = ctypes.create_string_buffer(128)
    local = Iovec(ctypes.addressof(out), 128)
    remote = Iovec(address, 128)
    size = native.process_vm_readv(pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
    if size <= 0:
        raise_errno("process_vm_readv")
    raw = out.raw[:size]
    end = raw.find(bytes([0]))
    if end < 0:
        raise RuntimeError("unterminated path")
    return raw[:end].decode("ascii", "strict")


def recvfd(sock):
    packet, anc, flags, _ = sock.recvmsg(512, socket.CMSG_SPACE(4), socket.MSG_CMSG_CLOEXEC)
    if packet != b"L":
        try:
            raise RuntimeError("listener transfer refused: " + repr(json.loads(packet)))
        except UnicodeDecodeError:
            raise RuntimeError("listener transfer refused: " + repr(packet))
    if flags & ~socket.MSG_CMSG_CLOEXEC:
        raise RuntimeError("listener packet flags")
    fds = []
    for level, kind, data in anc:
        if (level, kind) != (socket.SOL_SOCKET, socket.SCM_RIGHTS):
            raise RuntimeError("ancillary")
        values = array.array("i")
        values.frombytes(data)
        fds.extend(values)
    if len(fds) != 1:
        raise RuntimeError("listener count")
    return fds[0]


def maps(uid, gid):
    try:
        with open("/proc/self/setgroups", "w", encoding="ascii") as f:
            f.write("deny\n")
    except FileNotFoundError:
        pass
    with open("/proc/self/uid_map", "w", encoding="ascii") as f:
        f.write("0 %d 1\n" % uid)
    with open("/proc/self/gid_map", "w", encoding="ascii") as f:
        f.write("0 %d 1\n" % gid)
    if native.prctl(4, 1, 0, 0, 0) != 0:
        raise_errno("dumpable")


def dropcaps():
    with open("/proc/sys/kernel/cap_last_cap", encoding="ascii") as f:
        last = int(f.read())
    if not 0 <= last <= 63:
        raise RuntimeError("capability bounds")
    for number in range(last + 1):
        if native.prctl(24, number, 0, 0, 0) != 0:
            raise_errno("capability bound")
    if native.capset(ctypes.byref(CapHeader(0x20080522, 0)), (CapData * 2)()) != 0:
        raise_errno("capset")


def landlock():
    abi = native.syscall(444, 0, 0, 1)
    if abi < 6:
        raise RuntimeError("Landlock ABI below six")
    rootfd = os.open("/", os.O_PATH | O_CLOEXEC)
    rule = Ruleset((1 << 16) - 1, 3, 3)
    rules = native.syscall(444, ctypes.byref(rule), ctypes.sizeof(rule), 0)
    if rules < 0:
        raise_errno("create ruleset")
    try:
        path = PathRule(1 | 4 | 8, rootfd)
        if native.syscall(445, rules, 1, ctypes.byref(path), 0) != 0:
            raise_errno("add readonly root")
        if native.syscall(446, rules, 0) != 0:
            raise_errno("enforce Landlock")
    finally:
        os.close(rules)
        os.close(rootfd)
    try:
        fd = os.open("/proc/self/comm", O_WRONLY)
    except OSError as exc:
        if exc.errno != errno.EACCES:
            raise
    else:
        os.close(fd)
        raise RuntimeError("Landlock writable comm admitted")
    return abi


def mount(source, target, kind, flags, data=None):
    if native.mount(source, target, kind, ctypes.c_ulong(flags), data) != 0:
        raise_errno("mount")


def prepare_root(private_pid=False):
    uid = os.getuid()
    gid = os.getgid()
    base = tempfile.mkdtemp(prefix="hawedit-thread-proof-")
    if native.syscall(SYS_UNSHARE, CLONE_NEWUSER | 0x20000) != 0:
        raise_errno("private user/mount")
    maps(uid, gid)
    mount(None, b"/", None, 0x4000 | 0x40000)
    mount(b"tmpfs", base.encode("ascii"), b"tmpfs", 2 | 4, b"size=1048576,mode=0700")
    os.mkdir(base + "/proc", 0o500)
    if not private_pid:
        mount(b"/proc", (base + "/proc").encode("ascii"), None, 4096 | 16384)
    return base


def enter_root(base):
    os.chroot(base)
    os.chdir("/")


def controller_fence():
    denied = (
        41,
        42,
        43,
        49,
        50,
        53,
        272,
        308,
        165,
        166,
        155,
        161,
        428,
        429,
        430,
        431,
        432,
        433,
        442,
        435,
    )
    items = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, AUDIT_ARCH_X86_64),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
    ]
    for number in denied:
        items.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x50000 | errno.EPERM)])
    items.append((0x06, 0, 0, SECCOMP_RET_ALLOW))
    filters = (Filter * len(items))(*(Filter(*row) for row in items))
    prog = Program(len(filters), filters)
    if native.prctl(38, 1, 0, 0, 0) != 0:
        raise_errno("controller nnp")
    if native.syscall(SYS_SECCOMP, 1, 0, ctypes.byref(prog)) != 0:
        raise_errno("controller fence")
    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:
        if exc.errno != errno.EPERM:
            raise
    else:
        raise RuntimeError("controller network admitted")


def proc_check(fd):
    buf = (ctypes.c_long * 32)()
    if native.fstatfs(fd, ctypes.byref(buf)) != 0:
        raise_errno("fstatfs")
    if buf[0] != 0x9FA0:
        raise RuntimeError("task is not genuine procfs")


def run_case(use_userns, zero_caps=False, worker_landlock=False, private_root=None, mode="valid"):
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    worker = os.fork()
    if worker == 0:
        left.close()
        try:
            signal.alarm(12)
            if use_userns:
                uid = os.getuid()
                gid = os.getgid()
                if native.syscall(SYS_UNSHARE, CLONE_NEWUSER) != 0:
                    raise_errno("unshare user")
                maps(uid, gid)
            if private_root is not None:
                enter_root(private_root)
            if zero_caps:
                dropcaps()
            if native.prctl(38, 1, 0, 0, 0) != 0:
                raise_errno("no_new_privs")
            abi = landlock() if worker_landlock else None
            with open("/proc/self/status", encoding="ascii") as f:
                cap_status = {
                    k: v.strip()
                    for k, v in (line.split(":", 1) for line in f if line.startswith("Cap"))
                }
            if zero_caps and any(int(v, 16) for v in cap_status.values()):
                raise RuntimeError("nonzero capabilities")
            tid = []
            paths = []
            ready = threading.Event()
            go = threading.Event()
            done = threading.Event()
            finish = threading.Event()
            failure = []
            native.fopen.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            native.fopen.restype = ctypes.c_void_p
            native.fwrite.argtypes = [
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_size_t,
                ctypes.c_void_p,
            ]
            native.fwrite.restype = ctypes.c_size_t
            native.fclose.argtypes = [ctypes.c_void_p]
            native.fclose.restype = ctypes.c_int
            program = (Filter * 7)(
                Filter(0x20, 0, 0, 4),
                Filter(0x15, 1, 0, AUDIT_ARCH_X86_64),
                Filter(0x06, 0, 0, 0x80000000),
                Filter(0x20, 0, 0, 0),
                Filter(0x15, 0, 1, SYS_OPENAT),
                Filter(0x06, 0, 0, SECCOMP_RET_USER_NOTIF),
                Filter(0x06, 0, 0, SECCOMP_RET_ALLOW),
            )
            prog = Program(len(program), program)
            if native.prctl(38, 1, 0, 0, 0) != 0:
                raise_errno("no_new_privs")
            listener = native.syscall(
                SYS_SECCOMP,
                SECCOMP_SET_MODE_FILTER,
                SECCOMP_FILTER_FLAG_NEW_LISTENER,
                ctypes.byref(prog),
            )
            if listener < 0:
                raise_errno("listener")
            right.sendmsg(
                [b"L"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [listener]))]
            )
            os.close(listener)

            def target():
                try:
                    current = threading.get_native_id()
                    tid.append(current)
                    ready.set()
                    if mode == "vendor_shape":
                        if not finish.wait(8):
                            raise RuntimeError("vendor target completion timeout")
                        return
                    if not go.wait(5):
                        raise RuntimeError("target release timeout")
                    requested = "/proc/self/task/%d/comm" % current
                    if mode == "foreign":
                        requested = "/proc/%d/comm" % os.getppid()
                    if mode == "bad_path":
                        requested = "/proc/self/task/%d/status" % current
                    path = ctypes.create_string_buffer(requested.encode("ascii"), 128)
                    paths.append(path)
                    if mode == "unterminated":
                        path.raw = b"A" * 128
                    dirfd = AT_FDCWD if mode != "bad_dirfd" else -1
                    flags = EXPECTED_FLAGS if mode != "extra_flags" else EXPECTED_FLAGS | 1024
                    fd = native.syscall(SYS_OPENAT, dirfd, ctypes.byref(path), flags, 0o600)
                    if fd < 0:
                        right.send(
                            json.dumps(dict(refused_errno=ctypes.get_errno(), tid=current)).encode(
                                "ascii"
                            )
                        )
                    else:
                        try:
                            count = os.write(fd, b"HawUserns\n")
                        finally:
                            os.close(fd)
                        right.send(json.dumps(dict(write=count, tid=current)).encode("ascii"))
                    done.set()
                    if not finish.wait(5):
                        raise RuntimeError("completion timeout")
                except BaseException as exc:
                    failure.append((type(exc).__name__, str(exc)))
                    ready.set()
                    done.set()

            thread = threading.Thread(target=target)
            thread.start()
            if not ready.wait(5) or len(tid) != 1:
                raise RuntimeError("thread readiness " + repr(failure))
            right.send(
                json.dumps(
                    dict(
                        worker=os.getpid(),
                        tid=tid[0],
                        userns=use_userns,
                        caps=cap_status,
                        landlock_abi=abi,
                    )
                ).encode("ascii")
            )
            go.set()
            command = right.recv(16)
            if command == b"MUTATE":
                if len(paths) != 1:
                    raise RuntimeError("mutable path missing")
                paths[0].value = b"/proc/self/comm"
                right.send(b"MUTATED")
                command = right.recv(16)
            if command != b"GO":
                raise RuntimeError("no release")
            if mode == "vendor_shape":
                requested = ctypes.create_string_buffer(
                    ("/proc/self/task/%d/comm" % tid[0]).encode("ascii"), 128
                )
                stream = native.fopen(ctypes.cast(requested, ctypes.c_char_p), b"w")
                if not stream:
                    raise_errno("actual libc fopen")
                try:
                    data = b"VendorShape\n"
                    written = native.fwrite(ctypes.c_char_p(data), 1, len(data), stream)
                finally:
                    close_status = native.fclose(stream)
                if written != 12 or close_status != 0:
                    raise RuntimeError("actual libc write differs")
                right.send(
                    json.dumps(
                        dict(write=written, caller_tid=threading.get_native_id(), target_tid=tid[0])
                    ).encode("ascii")
                )
                done.set()
            if not done.wait(5):
                raise RuntimeError("write timeout")
            if failure:
                raise RuntimeError("target " + repr(failure))
            if right.recv(8) != b"DONE":
                raise RuntimeError("no completion")
            finish.set()
            thread.join(5)
            right.send(json.dumps(dict(ok=True)).encode("ascii"))
            os._exit(0)
        except BaseException as exc:
            try:
                right.send(
                    json.dumps(dict(ok=False, error=type(exc).__name__, message=str(exc))).encode(
                        "ascii"
                    )
                )
            finally:
                os._exit(71)
    right.close()
    original_pidfd = native.syscall(434, worker, 0)
    if original_pidfd < 0:
        raise_errno("original pidfd")
    listener = recvfd(left)
    case = dict(
        userns=use_userns,
        zero_caps=zero_caps,
        worker_landlock=worker_landlock,
        worker=worker,
        controller_pid=os.getpid(),
        mode=mode,
    )
    taskfd = -1
    threadfd = -1
    callerfd = -1
    try:
        metadata = json.loads(left.recv(1024))
        case["metadata"] = metadata
        if metadata["worker"] != worker:
            raise RuntimeError("direct original child differs")
        if select.select([original_pidfd], [], [], 0)[0]:
            raise RuntimeError("original worker exited")
        pidspace = fcntl.ioctl(original_pidfd, 0xFF05)
        userspace = fcntl.ioctl(original_pidfd, 0xFF09)
        userparent = -1
        try:
            original_pidspace = os.stat("/proc/self/ns/pid")
            original_userspace = os.stat("/proc/self/ns/user")
            if (os.fstat(pidspace).st_dev, os.fstat(pidspace).st_ino) != (
                original_pidspace.st_dev,
                original_pidspace.st_ino,
            ):
                raise RuntimeError("original pid namespace differs")
            if use_userns:
                userparent = fcntl.ioctl(userspace, 0xB702)
            expecteduser = userparent if use_userns else userspace
            if (os.fstat(expecteduser).st_dev, os.fstat(expecteduser).st_ino) != (
                original_userspace.st_dev,
                original_userspace.st_ino,
            ):
                raise RuntimeError("original user namespace relationship differs")
        finally:
            os.close(pidspace)
            os.close(userspace)
            if userparent >= 0:
                os.close(userparent)
        if private_root is not None:
            taskfd = os.open(
                "/proc/%d/task" % worker, os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
            )
            proc_check(taskfd)
            mount(None, (private_root + "/proc").encode("ascii"), None, 32 | 4096 | 1 | 2 | 4 | 8)
            mount(None, private_root.encode("ascii"), None, 32 | 1 | 2 | 4)
            enter_root(private_root)
            dropcaps()
            controller_fence()
            with open("/proc/self/status", encoding="ascii") as f:
                case["controller_caps"] = {
                    k: v.strip()
                    for k, v in (line.split(":", 1) for line in f if line.startswith("Cap"))
                }
            if any(int(v, 16) for v in case["controller_caps"].values()):
                raise RuntimeError("controller capabilities")
            case["readonly_root"] = bool(os.statvfs("/").f_flag & os.ST_RDONLY)
            case["readonly_proc"] = bool(os.statvfs("/proc").f_flag & os.ST_RDONLY)
            if not case["readonly_root"] or not case["readonly_proc"]:
                raise RuntimeError("root is writable")
            if os.path.exists("/home") or os.path.exists("/mnt"):
                raise RuntimeError("host path exposed")
        if mode == "vendor_shape":
            callerfd = os.open(
                str(worker), os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=taskfd
            )
            proc_check(callerfd)
            mainfd = os.open("comm", os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=callerfd)
            try:
                case["caller_comm_before"] = os.read(mainfd, 64).decode("ascii").strip()
            finally:
                os.close(mainfd)
            left.send(b"GO")
        buf = bytearray(80)
        fcntl.ioctl(listener, NOTIF_RECV, buf, True)
        ident, pid, flags = struct.unpack_from("<QII", buf, 0)
        number, arch, instruction, *args = struct.unpack_from("<iIQ6Q", buf, 16)
        try:
            requested = vmread(pid, args[1])
        except RuntimeError as exc:
            requested = None
            case["bounded_copy_refusal"] = str(exc)
        case.update(notification_pid=pid, syscall=number, arch=arch, requested=requested)
        admitted = bool(
            ident
            and pid == (worker if mode == "vendor_shape" else metadata["tid"])
            and flags == 0
            and number == SYS_OPENAT
            and arch == AUDIT_ARCH_X86_64
            and args[0] == (1 << 64) - 100
            and args[2] == EXPECTED_FLAGS
            and args[3] == (0o666 if mode == "vendor_shape" else 0o600)
            and requested == "/proc/self/task/%d/comm" % metadata["tid"]
        )
        case["request_admitted"] = admitted
        if admitted != (mode in ("valid", "mutable", "stale", "listener_loss", "vendor_shape")):
            raise RuntimeError("request validation differs from challenge")
        if mode == "vendor_shape":
            case.update(caller_tid=pid, target_tid=metadata["tid"], creation_mode=oct(args[3]))
            if pid == metadata["tid"]:
                raise RuntimeError("vendor calibration did not target another thread")
        fcntl.ioctl(listener, NOTIF_ID_VALID, struct.pack("<Q", ident))
        target = "/proc/%d/task/%d/comm" % (worker, metadata["tid"])
        if select.select([original_pidfd], [], [], 0)[0]:
            raise RuntimeError("original worker died before injection")
        threadfd = -1
        if taskfd >= 0:
            threadfd = os.open(
                str(metadata["tid"]),
                os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC,
                dir_fd=taskfd,
            )
            proc_check(threadfd)
        readfd = (
            os.open("comm", os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=threadfd)
            if threadfd >= 0
            else os.open(target, os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        )
        try:
            case["before_comm"] = os.read(readfd, 64).decode("ascii", "strict").strip()
        finally:
            os.close(readfd)
        if mode == "mutable":
            left.send(b"MUTATE")
            if left.recv(16) != b"MUTATED":
                raise RuntimeError("mutation acknowledgement")
            case["path_after_copy"] = vmread(pid, args[1])
            if case["path_after_copy"] == requested:
                raise RuntimeError("pathname did not change")
        if mode == "stale":
            source = (
                os.open("comm", O_WRONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=threadfd)
                if threadfd >= 0
                else os.open(target, O_WRONLY | O_NOFOLLOW | O_CLOEXEC)
            )
            try:
                if native.syscall(424, original_pidfd, signal.SIGKILL, 0, 0) != 0:
                    raise_errno("original worker drain")
                if not select.select([original_pidfd], [], [], 3)[0]:
                    raise RuntimeError("original exit not observed")
                case["exit"] = os.waitstatus_to_exitcode(os.waitpid(worker, 0)[1])
                for label, operation, payload in (
                    ("id_valid", NOTIF_ID_VALID, bytearray(struct.pack("<Q", ident))),
                    (
                        "addfd_send",
                        NOTIF_ADDFD,
                        bytearray(
                            struct.pack("<QIIII", ident, ADDFD_FLAG_SEND, source, 0, O_CLOEXEC)
                        ),
                    ),
                ):
                    try:
                        fcntl.ioctl(listener, operation, payload, True)
                    except OSError as exc:
                        if exc.errno != errno.ENOENT:
                            raise
                        case[label + "_errno"] = exc.errno
                    else:
                        raise RuntimeError("dead notification admitted")
                case["scope_drained"] = True
                return case
            finally:
                os.close(source)
        if not admitted or mode == "listener_loss":
            case["descriptor_injected"] = False
            if mode == "listener_loss":
                os.close(listener)
                listener = -1
            else:
                response = bytearray(struct.pack("<QqiI", ident, 0, -errno.EPERM, 0))
                fcntl.ioctl(listener, ioc(IOC_READ | IOC_WRITE, 1, 24), response, True)
            left.send(b"GO")
            case["worker_result"] = json.loads(left.recv(256))
            expected_error = errno.ENOSYS if mode == "listener_loss" else errno.EPERM
            if case["worker_result"].get("refused_errno") != expected_error:
                raise RuntimeError("kernel refusal differs")
            verify = (
                os.open("comm", os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=threadfd)
                if threadfd >= 0
                else os.open(target, os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
            )
            try:
                case["measured_comm"] = os.read(verify, 64).decode("ascii", "strict").strip()
            finally:
                os.close(verify)
            if case["measured_comm"] != case["before_comm"]:
                raise RuntimeError("refused task renamed")
            left.send(b"DONE")
            case["result"] = json.loads(left.recv(256))
            case["exit"] = os.waitstatus_to_exitcode(os.waitpid(worker, 0)[1])
            return case
        source = (
            os.open("comm", O_WRONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=threadfd)
            if threadfd >= 0
            else os.open(target, O_WRONLY | O_NOFOLLOW | O_CLOEXEC)
        )
        proc_check(source)
        try:
            payload = bytearray(struct.pack("<QIIII", ident, ADDFD_FLAG_SEND, source, 0, O_CLOEXEC))
            try:
                case["addfd_return"] = fcntl.ioctl(listener, NOTIF_ADDFD, payload, True)
                case["addfd_errno"] = None
            except OSError as exc:
                case["addfd_return"] = None
                case["addfd_errno"] = dict(errno=exc.errno, message=str(exc))
        finally:
            os.close(source)
        if case["addfd_errno"] is None:
            if mode != "vendor_shape":
                left.send(b"GO")
            case["worker_result"] = json.loads(left.recv(256))
            verify = (
                os.open("comm", os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=threadfd)
                if threadfd >= 0
                else os.open(target, os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
            )
            try:
                case["measured_comm"] = os.read(verify, 64).decode("ascii", "strict").strip()
            finally:
                os.close(verify)
            expected_name = "VendorShape" if mode == "vendor_shape" else "HawUserns"
            expected_count = 12 if mode == "vendor_shape" else 10
            if (
                case["measured_comm"] != expected_name
                or case["worker_result"]["write"] != expected_count
            ):
                raise RuntimeError("real comm measurement differs")
            if callerfd >= 0:
                mainfd = os.open("comm", os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC, dir_fd=callerfd)
                try:
                    case["measured_caller_comm"] = os.read(mainfd, 64).decode("ascii").strip()
                finally:
                    os.close(mainfd)
                if case["measured_caller_comm"] != case["caller_comm_before"]:
                    raise RuntimeError("wrong original thread renamed")
            left.send(b"DONE")
            case["result"] = json.loads(left.recv(256))
        else:
            response = bytearray(struct.pack("<QqiI", ident, 0, -errno.EPERM, 0))
            fcntl.ioctl(listener, ioc(IOC_READ | IOC_WRITE, 1, 24), response, True)
            left.send(b"GO")
            case["result"] = json.loads(left.recv(512))
        case["exit"] = os.waitstatus_to_exitcode(os.waitpid(worker, 0)[1])
        return case
    finally:
        if taskfd >= 0:
            os.close(taskfd)
        if threadfd >= 0:
            os.close(threadfd)
        if callerfd >= 0:
            os.close(callerfd)
        os.close(original_pidfd)
        if listener >= 0:
            os.close(listener)
        left.close()


results = []
for flags in ((False, False, False), (True, False, False), (True, True, False), (True, True, True)):
    try:
        results.append(run_case(*flags))
    except BaseException as exc:
        results.append(dict(flags=flags, probe_error=type(exc).__name__, message=str(exc)))
for private_pid, mode in (
    (False, "valid"),
    *(
        (True, mode)
        for mode in (
            "valid",
            "foreign",
            "extra_flags",
            "bad_dirfd",
            "bad_path",
            "unterminated",
            "mutable",
            "stale",
            "listener_loss",
            "vendor_shape",
        )
    ),
):
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    coordinator = os.fork()
    if coordinator == 0:
        parent.close()
        signal.alarm(15)
        try:
            base = prepare_root(private_pid)
            if private_pid:
                if native.syscall(SYS_UNSHARE, 0x20000000) != 0:
                    raise_errno("new pid namespace")
                inside = os.fork()
                if inside != 0:
                    child.close()
                    status = os.waitstatus_to_exitcode(os.waitpid(inside, 0)[1])
                    os._exit(status)
                signal.alarm(12)
                mount(b"proc", b"/proc", b"proc", 2 | 4 | 8)
                mount(b"/proc", (base + "/proc").encode("ascii"), None, 4096 | 16384)
            record = run_case(False, True, True, base, mode)
            record.update(private_root=True, private_pid=private_pid, base=base)
            child.send(json.dumps(record).encode("ascii"))
            os._exit(0)
        except BaseException as exc:
            try:
                child.send(
                    json.dumps(
                        dict(
                            private_root=True,
                            private_pid=private_pid,
                            mode=mode,
                            probe_error=type(exc).__name__,
                            message=str(exc),
                        )
                    ).encode("ascii")
                )
            finally:
                os._exit(72)
    child.close()
    results.append(json.loads(parent.recv(8192)))
    results[-1]["coordinator_exit"] = os.waitstatus_to_exitcode(os.waitpid(coordinator, 0)[1])
    parent.close()
    if "base" in results[-1]:
        base = results[-1]["base"]
        if not base.startswith("/tmp/hawedit-thread-proof-") or os.listdir(base):
            raise RuntimeError("private mount escaped or cleanup uncertain")
        os.rmdir(base)
        results[-1]["root_cleanup"] = True
print(
    json.dumps(
        dict(
            kind="seccomp-addfd-send-userns-boundary-matrix",
            kernel=os.uname().release,
            results=results,
        ),
        sort_keys=True,
    ),
    flush=True,
)
"""

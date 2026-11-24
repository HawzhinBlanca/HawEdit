"""Real stopped-worker tests using unchanged private-root setup, not model admission."""

from __future__ import annotations

import ast
from pathlib import Path


def program(case: str) -> str:
    source = Path(__file__).with_name("thread_name_kernel_probe.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "KERNEL_CODE" for target in node.targets
        )
    )
    assert isinstance(assignment, ast.Assign)
    code = ast.literal_eval(assignment.value)
    helpers = ast.parse(code)
    helpers.body = [
        node
        for node in helpers.body
        if isinstance(node, ast.Import | ast.ImportFrom | ast.ClassDef)
        or (isinstance(node, ast.FunctionDef) and node.name != "run_case")
        or (
            isinstance(node, ast.Assign)
            and not any(
                isinstance(target, ast.Name) and target.id == "results" for target in node.targets
            )
        )
        or (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "alarm"
        )
    ]
    return ast.unparse(helpers) + "\nCASE = " + repr(case) + "\n" + BODY


BODY = r"""
import time, traceback
from hawedit.linux_thread_registry import (
    LinuxThreadRegistry, LinuxThreadRegistryError, trace_original_worker,
)

def original_listener():
    rows = [
        (0x20,0,0,4), (0x15,1,0,AUDIT_ARCH_X86_64), (0x06,0,0,0x80000000),
        (0x20,0,0,0), (0x15,0,5,SYS_OPENAT), (0x20,0,0,32),
        (0x15,0,3,EXPECTED_FLAGS), (0x20,0,0,36), (0x15,0,1,0),
        (0x06,0,0,SECCOMP_RET_USER_NOTIF), (0x06,0,0,SECCOMP_RET_ALLOW),
    ]
    filters = (Filter * len(rows))(*(Filter(*row) for row in rows))
    current = native.syscall(SYS_SECCOMP,SECCOMP_SET_MODE_FILTER,
        SECCOMP_FILTER_FLAG_NEW_LISTENER,ctypes.byref(Program(len(rows),filters)))
    if current < 0:
        raise_errno('original notification listener')
    return current

parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
base = None
coordinator = os.fork()
if coordinator == 0:
    parent.close()
    report = {'case': CASE}
    try:
        base = prepare_root(True)
        if native.syscall(SYS_UNSHARE, 0x20000000) != 0:
            raise_errno('private pid namespace')
        inside = os.fork()
        if inside:
            child.close()
            os._exit(os.waitstatus_to_exitcode(os.waitpid(inside, 0)[1]))
        mount(b'proc', b'/proc', b'proc', 2 | 4 | 8)
        mount(b'/proc', (base + '/proc').encode('ascii'), None, 4096 | 16384)
        if CASE == 'exec':
            # Genuine sealed executable with an exit(42) entry point, not a ptrace rewrite.
            image = os.memfd_create('registry-real-exec',3)
            ident = b'\x7fELF\x02\x01\x01' + bytes(9)
            instructions = b'\xb8\x3c\x00\x00\x00\xbf\x2a\x00\x00\x00\x0f\x05'
            header = struct.pack('<16sHHIQQQIHHHHHH',ident,2,62,1,0x400078,64,0,0,64,56,1,0,0,0)
            segment = struct.pack('<IIQQQQQQ',1,5,0,0x400000,0,132,132,4096)
            assert os.write(image,header+segment+instructions) == 132
            os.fchmod(image,0o500)
            fcntl.fcntl(image,1033,15)
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        worker = os.fork()
        if worker == 0:
            left.close()
            child.close()
            try:
                enter_root(base)
                dropcaps()
                if native.prctl(38, 1, 0, 0, 0) != 0:
                    raise_errno('worker nnp')
                abi = landlock()
                right.send(b'LANDLOCK')
                if right.recv(16) != b'SEALED':
                    raise RuntimeError('root not sealed')
                if CASE == 'positive':
                    listener = original_listener()
                    right.sendmsg([b'L'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,
                        array.array('i',[listener]))])
                    os.close(listener)
                trace_original_worker()
                if CASE == 'exec':
                    right.send(json.dumps(dict(tid=2,landlock_abi=abi,
                        worker_refusals={})).encode('ascii'))
                    os.execve('/proc/self/fd/%d' % image,['registry-real-exec'],{})
                ready, finish = threading.Event(), threading.Event()
                tids = []
                def target():
                    tids.append(threading.get_native_id())
                    ready.set()
                    if not finish.wait(5):
                        os._exit(74)
                thread = threading.Thread(target=target)
                thread.start()
                additional = []
                if CASE == 'many':
                    for index in range(7):
                        item = threading.Thread(target=target)
                        item.start()
                        additional.append(item)
                if not ready.wait(5):
                    raise RuntimeError('unresumed original birth')
                refusals = {}
                for name, operation in (
                    ('ptrace', lambda: native.ptrace(0, 0, 0, 0)),
                    ('fork', lambda: native.syscall(57)),
                    ('vfork', lambda: native.syscall(58)),
                    ('clone3', lambda: native.syscall(435, 0, 0)),
                    ('process_clone', lambda: native.syscall(56, 17, 0, 0, 0, 0)),
                    ('untraced_clone', lambda: native.syscall(56,0x810900,0,0,0,0)),
                    ('ptrace_clone', lambda: native.syscall(56,0x12900,0,0,0,0)),
                ):
                    ctypes.set_errno(0)
                    value = operation()
                    code = ctypes.get_errno()
                    expected = errno.ENOSYS if name == 'clone3' else errno.EPERM
                    if value != -1 or code != expected:
                        raise RuntimeError('worker authority leaked: ' + name)
                    refusals[name] = code
                right.send(json.dumps(dict(tid=tids[0], landlock_abi=abi,
                    worker_refusals=refusals)).encode('ascii'))
                command = right.recv(16)
                if CASE == 'positive' and command == b'RENAME':
                    native.fopen.argtypes = [ctypes.c_char_p,ctypes.c_char_p]
                    native.fopen.restype = ctypes.c_void_p
                    native.fwrite.argtypes = [ctypes.c_void_p,ctypes.c_size_t,
                        ctypes.c_size_t,ctypes.c_void_p]
                    native.fwrite.restype = ctypes.c_size_t
                    native.fclose.argtypes = [ctypes.c_void_p]
                    native.fclose.restype = ctypes.c_int
                    stream = native.fopen(
                        ('/proc/self/task/%d/comm' % tids[0]).encode('ascii'),b'w')
                    if not stream:
                        raise_errno('genuine libc fopen')
                    count = native.fwrite(ctypes.c_char_p(b'Registered\n'),1,11,stream)
                    if count != 11 or native.fclose(stream) != 0:
                        raise RuntimeError('genuine worker comm write differs')
                    right.send(json.dumps(dict(written=count)).encode('ascii'))
                    command = right.recv(16)
                if command != b'DONE':
                    raise RuntimeError('completion token differs')
                finish.set()
                thread.join(5)
                for item in additional:
                    item.join(5)
                    if item.is_alive():
                        raise RuntimeError('original burst member not joined')
                if thread.is_alive():
                    raise RuntimeError('original thread not joined')
                os._exit(0)
            except BaseException as exc:
                try:
                    right.send(json.dumps(dict(worker_error=str(exc),
                        traceback=traceback.format_exc())).encode('ascii'))
                finally:
                    os._exit(71)
        right.close()
        original_pidfd = os.pidfd_open(worker, 0)
        taskfd = os.open('/proc/%d/task' % worker,
            os.O_RDONLY | os.O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        if left.recv(16) != b'LANDLOCK':
            raise RuntimeError('mandatory worker Landlock missing')
        mount(None, (base + '/proc').encode('ascii'), None, 32 | 4096 | 1 | 2 | 4 | 8)
        mount(None, base.encode('ascii'), None, 32 | 1 | 2 | 4)
        enter_root(base)
        dropcaps()
        controller_fence()
        report.update(base=base, readonly_root=bool(os.statvfs('/').f_flag & os.ST_RDONLY),
            readonly_proc=bool(os.statvfs('/proc').f_flag & os.ST_RDONLY))
        left.send(b'SEALED')
        listener = recvfd(left) if CASE == 'positive' else -1
        registry = LinuxThreadRegistry(original_pidfd, taskfd,
            max_threads=1 if CASE == 'budget' else 64,
            timeout_seconds=1 if CASE == 'timeout' else 5)
        metadata = None
        end = time.monotonic() + 6
        while metadata is None:
            if time.monotonic() >= end:
                raise RuntimeError('original kernel test deadline')
            try:
                registry.poll()
            except LinuxThreadRegistryError as exc:
                if CASE != 'budget':
                    raise
                report['refusal'] = str(exc)
                break
            if select.select([left], [], [], 0.001)[0]:
                metadata = json.loads(left.recv(8192))
                if 'worker_error' in metadata:
                    raise RuntimeError(metadata)
        if metadata:
            report['metadata'] = metadata
            report['registered'] = list(registry.registered_tids)
            report['event_count_before_use'] = registry.event_count
            assert worker in registry.registered_tids
            assert metadata['tid'] in registry.registered_tids
            if CASE in ('many','exec'):
                if CASE == 'many':
                    left.send(b'DONE')
            elif CASE in ('substituted', 'reopened', 'closed'):
                primary = registry._tasks[metadata['tid']].fd
                if CASE == 'closed':
                    os.close(primary)
                elif CASE == 'substituted':
                    foreign = os.open('/proc/1/task/1',
                        os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
                else:
                    foreign = os.open(str(metadata['tid']),
                        os.O_RDONLY | os.O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC, dir_fd=taskfd)
                    report['same_inode'] = os.fstat(primary).st_ino == os.fstat(foreign).st_ino
                if CASE != 'closed':
                    os.dup2(foreign, primary, inheritable=False)
                try:
                    registry.open_comm(worker, metadata['tid'])
                except LinuxThreadRegistryError as exc:
                    report['refusal'] = str(exc)
                else:
                    raise RuntimeError('substituted description admitted')
            elif CASE == 'foreign':
                refusals = []
                for caller, target in ((worker, 1), (1, metadata['tid']),
                    (worker, 999999), (True, metadata['tid'])):
                    try:
                        registry.open_comm(caller, target)
                    except LinuxThreadRegistryError as exc:
                        refusals.append(str(exc))
                    else:
                        raise RuntimeError('unregistered target admitted')
                report['refusals'] = refusals
                left.send(b'DONE')
            elif CASE == 'timeout':
                time.sleep(1.1)
                try:
                    registry.open_comm(worker, metadata['tid'])
                except LinuxThreadRegistryError as exc:
                    report['refusal'] = str(exc)
                else:
                    raise RuntimeError('deadline ignored')
            elif CASE == 'trace':
                records = []
                ptrace = native.ptrace
                ptrace.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
                ptrace.restype = ctypes.c_long
                for request, target, address, data in (
                    *((request, worker, 0, 0) for request in (2,5,12,13,16,17,24,16902,16910)),
                    (7,worker,0,9),(16896,worker,0,0),(16897,worker,1,0),
                    (7,1,0,0),(7,worker,1,0),(7,worker,0,1 << 32),
                ):
                    ctypes.set_errno(0)
                    value = ptrace(request,target,ctypes.c_void_p(address),ctypes.c_void_p(data))
                    code = ctypes.get_errno()
                    if value != -1 or code != errno.EPERM:
                        raise RuntimeError('unapproved tracing admitted ' +
                            repr((request,target,address,data,value,code)))
                    records.append(dict(request=request,target=target,address=address,data=data,errno=code))
                report['trace_refusals'] = records
                left.send(b'DONE')
            elif CASE == 'stale':
                registry.stop()
                try:
                    registry.open_comm(worker, metadata['tid'])
                except LinuxThreadRegistryError as exc:
                    report['refusal'] = str(exc)
                else:
                    raise RuntimeError('dead original task admitted')
            else:
                left.send(b'RENAME')
                if not select.select([listener],[],[],1)[0]:
                    raise RuntimeError('actual fopen notification missing')
                notification = bytearray(80)
                fcntl.ioctl(listener,NOTIF_RECV,notification,True)
                ident,pid,flags = struct.unpack_from('<QII',notification,0)
                number,arch,instruction,*args = struct.unpack_from('<iIQ6Q',notification,16)
                fcntl.ioctl(listener,NOTIF_ID_VALID,struct.pack('<Q',ident))
                assert ident and pid == worker and flags == 0
                assert number == SYS_OPENAT and arch == AUDIT_ARCH_X86_64
                assert args[0] == (1 << 64) - 100
                assert args[2] == EXPECTED_FLAGS and args[3] == 0o666
                assert vmread(pid,args[1]) == '/proc/self/task/%d/comm' % metadata['tid']
                current = registry.open_comm(worker, metadata['tid'])
                try:
                    fcntl.ioctl(listener,NOTIF_ID_VALID,struct.pack('<Q',ident))
                    report['injected_fd'] = fcntl.ioctl(listener,NOTIF_ADDFD,
                        bytearray(struct.pack('<QIIII',ident,ADDFD_FLAG_SEND,current,0,0)),True)
                finally:
                    os.close(current)
                report['write_result'] = json.loads(left.recv(8192))
                current = os.open('comm', os.O_RDONLY | O_NOFOLLOW | O_CLOEXEC,
                    dir_fd=registry._tasks[metadata['tid']].fd)
                try:
                    report['measured_comm'] = os.read(current,64).decode('ascii').strip()
                finally:
                    os.close(current)
                left.send(b'DONE')
        if CASE in ('substituted','reopened','closed','stale','budget','timeout'):
            registry.stop()
        else:
            while not registry.drained:
                if time.monotonic() >= end:
                    raise RuntimeError('registered members not reaped')
                registry.poll()
                time.sleep(0.001)
        report.update(registered=list(registry.registered_tids),
            observed=list(registry.observed_tids), reaped=list(registry.reaped_tids),
            drained=registry.drained, worker_exit=registry.worker_exit,
            exec_count=registry.exec_count)
        try:
            registry.close()
        except LinuxThreadRegistryError as exc:
            if CASE not in ('substituted','reopened','closed'):
                raise
            report['cleanup_refusal'] = str(exc)
        if CASE in ('substituted','reopened'):
            report['foreign_preserved'] = fcntl.fcntl(primary,1027,foreign) == 1
            os.close(primary)
            os.close(foreign)
        os.close(taskfd)
        os.close(original_pidfd)
        if CASE == 'exec':
            os.close(image)
        if listener >= 0:
            os.close(listener)
        left.close()
        child.send(json.dumps(report).encode('ascii'))
        os._exit(0)
    except BaseException as exc:
        try:
            child.send(json.dumps(dict(report=report, error=str(exc),
                traceback=traceback.format_exc())).encode('ascii'))
        finally:
            os._exit(72)
child.close()
if not select.select([parent],[],[],10)[0]:
    raise RuntimeError('original controller reply timeout')
record = json.loads(parent.recv(65536))
record['coordinator_exit'] = os.waitstatus_to_exitcode(os.waitpid(coordinator,0)[1])
parent.close()
base = record.get('base',record.get('report',{}).get('base'))
if base:
    if not base.startswith('/tmp/hawedit-thread-proof-') or os.listdir(base):
        raise RuntimeError('private root cleanup uncertain')
    os.rmdir(base)
    record['root_cleanup'] = True
record['kernel'] = os.uname().release
print(json.dumps(record,sort_keys=True),flush=True)
"""

"""Real kernel broker challenges over the unchanged stopped-worker fixture."""

from __future__ import annotations

import ast

from original_registry_kernel_probe import program


def broker_program(case: str) -> str:
    tree = ast.parse(program("positive"))
    tree.body[0:0] = ast.parse(
        "from dataclasses import asdict\n"
        "from hawedit.linux_thread_name import LinuxThreadNameBroker,LinuxThreadNameError\n"
        "BROKER_CASE = " + repr(case)
    ).body
    listener = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "original_listener"
    )
    rows = next(node for node in listener.body if isinstance(node, ast.Assign))
    rows.value = ast.parse(
        "[(0x20,0,0,4),(0x15,1,0,AUDIT_ARCH_X86_64),(0x06,0,0,0x80000000),"
        "(0x20,0,0,0),(0x15,0,3,SYS_OPENAT),(0x20,0,0,32),"
        "(0x45,0,1,O_CREAT|O_TRUNC|os.O_APPEND),"
        "(0x06,0,0,SECCOMP_RET_USER_NOTIF),(0x06,0,0,SECCOMP_RET_ALLOW)]",
        mode="eval",
    ).body
    stale = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "CASE == 'stale'"
    )
    assert stale.orelse
    stale.orelse = ast.parse(BROKER_OPERATION).body
    if case == "foreign":
        fopen = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "native.fopen"
        )
        fopen.args[0] = ast.Constant(b"/proc/self/task/1/comm")
    failure = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and any(keyword.arg == "worker_error" for keyword in node.keywords)
    )
    failure.keywords.append(
        ast.keyword(arg="errno", value=ast.parse("getattr(exc,'errno',None)", mode="eval").body)
    )
    rename = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "CASE == 'positive' and command == b'RENAME'"
    )
    original = rename.body
    rename.body = ast.parse(RAW_REFUSAL).body
    assert isinstance(rename.body[0], ast.If)
    rename.body[0].orelse = original
    close = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and ast.unparse(node.body[0].value) == "registry.close()"
    )
    close.body[0:0] = ast.parse(
        "if broker is not None:\n"
        " try:broker.close()\n"
        " except LinuxThreadNameError as exc:\n"
        "  if BROKER_CASE!='substitution':raise\n"
        "  report['broker_cleanup_refusal']=str(exc)\n"
        "  report['foreign_preserved']=fcntl.fcntl(listener,1027,foreign)==1\n"
        "  os.close(foreign)\n"
    ).body
    code = ast.unparse(ast.fix_missing_locations(tree))
    compile(code, "<real-source-thread-broker>", "exec")
    return code


BROKER_OPERATION = r"""
broker = None
if BROKER_CASE == 'bad_listener':
    try:
        LinuxThreadNameBroker(registry, taskfd)
    except LinuxThreadNameError as exc:
        report['broker_refusal'] = str(exc)
    else:
        raise RuntimeError('non-listener admitted')
    registry.stop()
else:
    broker = LinuxThreadNameBroker(registry,listener,
        timeout_seconds=0.1 if BROKER_CASE in ('idle','existing_timer') else 5)
    if BROKER_CASE == 'substitution':
        foreign = os.open('comm',os.O_RDONLY|O_CLOEXEC|O_NOFOLLOW,
            dir_fd=registry._tasks[worker].fd)
        os.dup2(foreign,listener,inheritable=False)
        try:
            broker.serve_once()
        except LinuxThreadNameError as exc:
            report['broker_refusal']=str(exc)
        else:
            raise RuntimeError('substituted listener admitted')
        registry.stop()
    elif BROKER_CASE in ('idle','existing_timer','earlier_timer',
        'periodic_timer','foreign_handler'):
        before=time.monotonic()
        previous_handler=signal.getsignal(signal.SIGALRM)
        if BROKER_CASE=='existing_timer':
            signal.setitimer(signal.ITIMER_REAL,1)
        if BROKER_CASE=='earlier_timer':
            signal.setitimer(signal.ITIMER_REAL,0.05)
        if BROKER_CASE=='periodic_timer':
            signal.setitimer(signal.ITIMER_REAL,1,1)
        if BROKER_CASE=='foreign_handler':
            def original_watchdog(signum,frame):
                raise RuntimeError('foreign controller watchdog unexpectedly invoked')
            signal.signal(signal.SIGALRM,original_watchdog)
            previous_handler=original_watchdog
        try:
            broker.serve_once()
        except LinuxThreadNameError as exc:
            report['broker_refusal']=str(exc)
            report['idle_elapsed_s']=time.monotonic()-before
        else:
            raise RuntimeError('empty receive returned a fabricated result')
        report['handler_restored']=signal.getsignal(signal.SIGALRM)==previous_handler
        report['timer_restored']=signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)
        if BROKER_CASE=='existing_timer':
            report['remaining_original_timer']=signal.getitimer(signal.ITIMER_REAL)[0]
            signal.setitimer(signal.ITIMER_REAL,0)
        if BROKER_CASE=='periodic_timer':
            report['periodic_remaining']=signal.getitimer(signal.ITIMER_REAL)
            signal.setitimer(signal.ITIMER_REAL,0)
        if BROKER_CASE=='foreign_handler':
            signal.signal(signal.SIGALRM,signal.SIG_DFL)
        registry.stop()
    else:
        left.send(b'RENAME')
        result=broker.serve_once()
        report['broker_result']=asdict(result)
        report['write_result']=json.loads(left.recv(8192))
        if BROKER_CASE in ('foreign','flags','mode','dirfd','path'):
            if result.accepted or result.descriptor is not None:
                raise RuntimeError('foreign thread injected')
            if BROKER_CASE != 'foreign':
                left.send(b'DONE')
        else:
            if not result.accepted or result.descriptor is None:
                raise RuntimeError('genuine original fopen refused')
            current=os.open('comm',os.O_RDONLY|O_NOFOLLOW|O_CLOEXEC,
                dir_fd=registry._tasks[metadata['tid']].fd)
            try:
                report['measured_comm']=os.read(current,64).decode('ascii').strip()
            finally:
                os.close(current)
            left.send(b'DONE')
"""

RAW_REFUSAL = r"""
if BROKER_CASE in ('flags','mode','dirfd','path'):
    requested=('/proc/self/task/%d/comm' % tids[0]).encode('ascii')
    if BROKER_CASE=='path':
        requested=('/proc/self/task/00%d/comm' % tids[0]).encode('ascii')
    ctypes.set_errno(0)
    returned=native.syscall(257,ctypes.c_long(0 if BROKER_CASE=='dirfd' else -100),
        ctypes.c_char_p(requested),ctypes.c_long(EXPECTED_FLAGS |
        (os.O_APPEND if BROKER_CASE=='flags' else 0)),
        ctypes.c_long(0o600 if BROKER_CASE=='mode' else 0o666))
    code=ctypes.get_errno()
    if returned>=0:
        os.close(returned)
        raise RuntimeError('non-exact request injected a descriptor')
    if code!=errno.EPERM:
        raise RuntimeError('genuine request refusal differs')
    right.send(json.dumps(dict(refused_errno=code)).encode('ascii'))
    command=right.recv(16)
"""

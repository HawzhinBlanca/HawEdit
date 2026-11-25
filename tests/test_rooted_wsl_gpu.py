"""Native fixed-endpoint controls, never model/resource/producer admission."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from test_rooted_linux_image import _rooted_run

_ADMIT = (
    "from hawedit.linux_snapshot import SnapshotMode\n"
    "os.set_inheritable(channel.fileno(),False)\n"
    "snapshot=LinuxSnapshot(root,(*runtime_files,"
    "SnapshotFile(source,'input.bin',sha,len(original))),"
    "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True,wsl_gpu=True,"
    "control_fds=(channel.fileno(),),max_bytes=8388608)\n"
)


def _gpu_run(tmp_path: Path, action: str, *, before: str = "", parent: str = "") -> None:
    # Unsupported hosts must actually refuse, not silently skip a positive test.
    _rooted_run(
        tmp_path,
        before + "\nimport ctypes,fcntl\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "native=LinuxSnapshot._libc()\n"
        "abi=native.syscall(444,0,0,1)\n"
        "device=Path('/dev/dxg')\n"
        "supported=abi>=6 and device.exists()\n"
        "if supported:\n"
        " info=device.stat(follow_symlinks=False)\n"
        " supported=stat.S_ISCHR(info.st_mode) and info.st_rdev==os.makedev(10,258)\n"
        "if not supported:\n"
        " os.set_inheritable(channel.fileno(),False)\n"
        " try:\n"
        "  LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'input.bin',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True,wsl_gpu=True,"
        "control_fds=(channel.fileno(),),max_bytes=8388608)\n"
        " except LinuxSnapshotError as exc:assert exc.__cause__ is not None\n"
        " else:raise AssertionError('Unsupported GPU boundary admitted')\n"
        "else:\n" + "\n".join(" " + line for line in action.splitlines()),
        parent=parent,
    )


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_private_wsl_gpu_refuses_invalid_type(tmp_path: Path, value: object) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    file = module.SnapshotFile(tmp_path / "source", "input.bin", "0" * 64, 1)
    with pytest.raises(module.LinuxSnapshotError):
        module.LinuxSnapshot._declarations(
            tmp_path, (file,), 8388608, 4096, module.SnapshotMode.ROOTED_IMAGE, True, value, ()
        )


@pytest.mark.parametrize("name", ["dev", "dev/dxg", "dev/dxg/foreign"])
def test_private_wsl_gpu_refuses_reserved_collision(tmp_path: Path, name: str) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    file = module.SnapshotFile(tmp_path / "source", name, "0" * 64, 1)
    with pytest.raises(module.LinuxSnapshotError):
        module.LinuxSnapshot._declarations(
            tmp_path, (file,), 8388608, 4096, module.SnapshotMode.ROOTED_IMAGE, True, True, ()
        )


@pytest.mark.parametrize("rooted,entropy", [(False, False), (False, True), (True, False)])
def test_private_wsl_gpu_requires_root_and_entropy(
    tmp_path: Path, rooted: bool, entropy: bool
) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    file = module.SnapshotFile(tmp_path / "source", "input.bin", "0" * 64, 1)
    mode = module.SnapshotMode.ROOTED_IMAGE if rooted else module.SnapshotMode.DATA_ONLY
    with pytest.raises(module.LinuxSnapshotError):
        module.LinuxSnapshot._declarations(
            tmp_path, (file,), 8388608, 4096, mode, entropy, True, ()
        )


def test_snapshot_default_excludes_private_wsl_gpu(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "snapshot=LinuxSnapshot(root,tuple(runtime_files),mode=SnapshotMode.ROOTED_IMAGE)\n"
        "assert not Path('/dev/dxg').exists()\n"
        "snapshot.verify();snapshot.close()",
    )


def test_private_wsl_gpu_requires_original_character_description(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "assert snapshot._gpu is not None\n"
        "first,anchor=snapshot._gpu\n"
        "assert fcntl.fcntl(first,1027,anchor)==1\n"
        "for fd in (first,anchor):\n"
        " info=os.fstat(fd)\n"
        " assert stat.S_ISCHR(info.st_mode) and info.st_rdev==os.makedev(10,258)\n"
        " assert fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_PATH and not os.get_inheritable(fd)\n"
        " try:os.read(fd,1)\n"
        " except OSError as exc:assert exc.errno==errno.EBADF\n"
        " else:raise AssertionError('Original O_PATH device performed I/O')\n"
        "assert os.stat('/dev/dxg').st_ino==os.fstat(first).st_ino\n"
        "flags=os.statvfs('/dev/dxg').f_flag\n"
        "assert flags&os.ST_NOSUID and flags&os.ST_NOEXEC and not flags&os.ST_NODEV\n"
        "assert os.statvfs('/').f_flag&os.ST_RDONLY and os.statvfs('/').f_flag&os.ST_NODEV\n"
        "opened=os.open('/dev/dxg',os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW)\n"
        "assert os.fstat(opened).st_ino==os.fstat(first).st_ino;os.close(opened)\n"
        "snapshot.verify();snapshot.close()",
    )


def test_private_gpu_policy_preserves_entropy_and_file_write_refusal(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "assert snapshot._entropy is not None\n"
        "for path in ('/dev/urandom','/input.bin',"
        "'/proc/self/fd/'+str(snapshot._entropy[0])):\n"
        " for flags in (os.O_WRONLY,os.O_RDWR):\n"
        "  try:fd=os.open(path,flags|os.O_CLOEXEC)\n"
        "  except OSError as exc:assert exc.errno in (errno.EACCES,errno.EROFS)\n"
        "  else:os.close(fd);raise AssertionError('Non-GPU writable open admitted')\n"
        "fd=os.open('/dev/urandom',os.O_RDONLY|os.O_CLOEXEC)\n"
        "assert len(os.read(fd,32))==32\n"
        "try:fcntl.ioctl(fd,0x80045200,bytearray(4),True)\n"
        "except OSError as exc:assert exc.errno==errno.EACCES\n"
        "else:raise AssertionError('Non-GPU device ioctl admitted')\n"
        "os.close(fd)\n"
        "assert snapshot.path('input.bin').read_bytes()==original\n"
        "snapshot.verify();snapshot.close()",
    )


def test_private_gpu_policy_preserves_async_and_namespace_fence(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "for number in (425,426,427,437,435):\n"
        " ctypes.set_errno(0);assert native.syscall(number,0,0,0,0,0,0)==-1\n"
        " assert ctypes.get_errno()==errno.ENOSYS\n"
        "ctypes.set_errno(0);assert native.unshare(0x10000000)==-1\n"
        "assert ctypes.get_errno()==errno.EPERM\n"
        "for flags in (os.O_CREAT,os.O_TRUNC,os.O_APPEND):\n"
        " try:fd=os.open('/dev/dxg',flags|os.O_RDWR|os.O_CLOEXEC)\n"
        " except OSError as exc:assert exc.errno==errno.EPERM\n"
        " else:os.close(fd);raise AssertionError('Dangerous GPU open flags admitted')\n"
        "snapshot.verify();snapshot.close()",
    )


@pytest.mark.parametrize("number", [444, 445, 446])
def test_private_wsl_gpu_requires_enforced_policy_before_release(
    tmp_path: Path, number: int
) -> None:
    _gpu_run(
        tmp_path,
        "from hawedit.linux_snapshot import _Filter,_Program\n"
        "rules=(_Filter*4)(_Filter(0x20,0,0,0),"
        f"_Filter(0x15,0,1,{number}),"
        "_Filter(0x06,0,0,0x50000|errno.EPERM),_Filter(0x06,0,0,0x7fff0000))\n"
        "program=_Program(len(rules),rules)\n"
        "assert native.prctl(22,2,ctypes.addressof(program),0,0)==0\n"
        "try:\n" + "\n".join(" " + line for line in _ADMIT.splitlines()) + "\n"
        "except LinuxSnapshotError as exc:\n"
        " assert isinstance(exc.__cause__,OSError) and exc.__cause__.errno==errno.EPERM\n"
        "else:raise AssertionError('Kernel-denied mandatory policy admitted')",
    )


def test_private_gpu_policy_refuses_external_network_and_foreign_handles(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "for domain in (socket.AF_INET,socket.AF_INET6,socket.AF_NETLINK):\n"
        " try:opened=socket.socket(domain,socket.SOCK_STREAM)\n"
        " except OSError as exc:assert exc.errno==errno.EPERM\n"
        " else:opened.close();raise AssertionError('External socket domain admitted')\n"
        "left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "left.send(b'private');assert right.recv(32)==b'private';left.close();right.close()\n"
        "snapshot.verify();snapshot.close()",
    )


@pytest.mark.parametrize("kind", ["socket", "device", "entropy"])
def test_private_gpu_policy_refuses_preexisting_foreign_handles(tmp_path: Path, kind: str) -> None:
    acquisitions = {
        "socket": "foreign=socket.socket(socket.AF_INET,socket.SOCK_STREAM);fd=foreign.fileno()",
        "device": "fd=os.open('/dev/dxg',os.O_PATH|os.O_CLOEXEC|os.O_NOFOLLOW)",
        "entropy": "fd=os.open('/dev/urandom',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)",
    }
    _gpu_run(
        tmp_path,
        acquisitions[kind]
        + "\ntry:\n"
        + "\n".join(" " + line for line in _ADMIT.splitlines())
        + "\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Pre-policy foreign description admitted')\n"
        "os.fstat(fd)\n" + ("foreign.close()" if kind == "socket" else "os.close(fd)"),
    )


def test_private_wsl_gpu_refuses_reopened_description_and_preserves_foreign_fd(
    tmp_path: Path,
) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "assert snapshot._gpu is not None\n"
        "first,anchor=snapshot._gpu\n"
        "identity=os.fstat(first);os.close(first)\n"
        "replaced=os.open('/dev/dxg',os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC)\n"
        "assert replaced==first and os.fstat(replaced).st_ino==identity.st_ino\n"
        "assert fcntl.fcntl(first,1027,anchor)==0\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Same inode reopened description admitted')\n"
        "snapshot.close();assert os.fstat(replaced).st_ino==identity.st_ino;os.close(replaced)",
    )


def test_private_gpu_policy_survives_fork_and_threads(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "def refused():\n"
        " try:fd=os.open('/dev/urandom',os.O_RDWR)\n"
        " except OSError as exc:assert exc.errno==errno.EACCES\n"
        " else:os.close(fd);raise AssertionError('Child lost kernel policy')\n"
        "refused();outcomes=[]\n"
        "def worker():refused();outcomes.append('refused')\n"
        "thread=threading.Thread(target=worker);thread.start();thread.join(3)\n"
        "assert not thread.is_alive() and outcomes==['refused']\n"
        "child=os.fork()\n"
        "if child==0:\n"
        " try:refused()\n"
        " except BaseException:os._exit(2)\n"
        " os._exit(0)\n"
        "assert os.waitstatus_to_exitcode(os.waitpid(child,0)[1])==0\n"
        "snapshot.verify();snapshot.close()",
    )


@pytest.mark.parametrize("controls", [None, [], (True,), (2,), (5, 5), "5"])
def test_private_wsl_gpu_refuses_invalid_control_declarations(
    tmp_path: Path, controls: object
) -> None:
    module = importlib.import_module("hawedit.linux_snapshot")
    file = module.SnapshotFile(tmp_path / "source", "input.bin", "0" * 64, 1)
    with pytest.raises(module.LinuxSnapshotError):
        module.LinuxSnapshot._declarations(
            tmp_path, (file,), 8388608, 4096, module.SnapshotMode.ROOTED_IMAGE, True, True, controls
        )


@pytest.mark.parametrize("fault", ["missing", "inheritable"])
def test_private_gpu_policy_refuses_unproven_control_channel(tmp_path: Path, fault: str) -> None:
    admission = _ADMIT.replace("os.set_inheritable(channel.fileno(),False)\n", "")
    if fault == "missing":
        admission = admission.replace("control_fds=(channel.fileno(),)", "control_fds=()")
    _gpu_run(
        tmp_path,
        "try:\n" + "\n".join(" " + line for line in admission.splitlines()) + "\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Unproven original control channel admitted')\n"
        "channel.fileno();os.fstat(channel.fileno())",
    )


def test_private_gpu_policy_refuses_incoming_handle_transfer(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
        "opened=os.open('/dev/urandom',os.O_RDONLY|os.O_CLOEXEC)\n"
        "import array\n"
        "left.sendmsg([b'foreign'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[opened]))])\n"
        "try:right.recvmsg(32,socket.CMSG_SPACE(4))\n"
        "except OSError as exc:assert exc.errno==errno.EPERM\n"
        "else:raise AssertionError('New foreign description transferred after policy')\n"
        "os.close(opened);left.close();right.close()\n"
        "snapshot.verify();snapshot.close()",
    )


def test_private_gpu_policy_refuses_outside_abstract_socket(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "outside=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
        "try:outside.connect(chr(0)+'hawedit-gpu-'+source.parent.name)\n"
        "except OSError as exc:assert exc.errno==errno.EPERM\n"
        "else:raise AssertionError('Outside abstract socket reached')\n"
        "outside.close();snapshot.verify();snapshot.close()",
        before="channel.send(b'server-needed');assert channel.recv(32)==b'continue'",
        parent="assert select.select([left],[],[],8)[0]\n"
        "assert left.recv(32)==b'server-needed'\n"
        "server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
        "server.bind(chr(0)+'hawedit-gpu-'+base.name);server.listen(1)\n"
        "control=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
        "control.connect(server.getsockname());peer,_=server.accept();peer.close();control.close()\n"
        "left.send(b'continue')",
    )


@pytest.mark.parametrize("fault", ["policy", "device"])
def test_private_gpu_policy_refuses_endpoint_or_policy_drift(tmp_path: Path, fault: str) -> None:
    damage = (
        "snapshot._gpu_policy=None"
        if fault == "policy"
        else "first=snapshot._gpu[0];replacement=os.open('/dev/urandom',os.O_PATH|os.O_CLOEXEC);"
        "os.dup2(replacement,first,inheritable=False);os.close(replacement)"
    )
    _gpu_run(
        tmp_path,
        _ADMIT + "assert snapshot._gpu is not None\n" + damage + "\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Device/policy custody drift admitted')\n"
        "snapshot.close()",
    )


def test_private_gpu_policy_survives_exec(tmp_path: Path) -> None:
    consumer = (
        "import errno,os\n"
        "try:fd=os.open('/dev/urandom',os.O_RDWR)\n"
        "except OSError as exc:assert exc.errno==errno.EACCES\n"
        "else:os.close(fd);raise AssertionError('Exec lost leaf policy')\n"
        "fd=os.open('/dev/dxg',os.O_RDWR|os.O_CLOEXEC)\n"
        "assert os.fstat(fd).st_rdev==os.makedev(10,258);os.close(fd)\n"
        "print('policy-retained')\n"
    )
    _gpu_run(
        tmp_path,
        "import subprocess,sysconfig\n"
        "files=list(runtime_files);names={item.relative_path for item in files}\n"
        "def declare(path,name):\n"
        " if name in names:return\n"
        " actual=path.resolve(strict=True);data=actual.read_bytes();names.add(name)\n"
        " files.append(SnapshotFile(actual,name,hashlib.sha256(data).hexdigest(),"
        "len(data),executable=data[:4]==b'\\x7fELF'))\n"
        "stdlib=Path(sysconfig.get_path('stdlib'))\n"
        "for parent,dirs,entries in os.walk(stdlib,followlinks=False):\n"
        " dirs[:]=sorted(name for name in dirs if name not in "
        "('site-packages','dist-packages','__pycache__'))\n"
        " for name in sorted(entries):\n"
        "  path=Path(parent)/name;declare(path,str(path).lstrip('/'))\n"
        "executable=Path(sys.executable).resolve(strict=True)\n"
        "declare(executable,str(executable).lstrip('/'))\n"
        "for row in Path('/proc/self/maps').read_text().splitlines():\n"
        " fields=row.split(maxsplit=5)\n"
        " if len(fields)==6 and fields[5].startswith('/'):\n"
        "  path=Path(fields[5]);declare(path,str(path).lstrip('/'))\n"
        "  for alias in path.parent.iterdir():\n"
        "   if alias.is_symlink() and alias.resolve()==path.resolve():\n"
        "    declare(alias,str(alias).lstrip('/'))\n"
        "declare(Path('/lib64/ld-linux-x86-64.so.2'),'lib64/ld-linux-x86-64.so.2')\n"
        "os.set_inheritable(channel.fileno(),False)\n"
        "snapshot=LinuxSnapshot(root,tuple(files),mode=SnapshotMode.ROOTED_IMAGE,"
        "kernel_entropy=True,wsl_gpu=True,control_fds=(channel.fileno(),),"
        "max_bytes=512*1024**2,max_files=6000)\n"
        f"result=subprocess.run([str(executable),'-I','-B','-c',{consumer!r}],"
        "capture_output=True,timeout=3,check=False)\n"
        "assert result.returncode==0,result.stderr\n"
        "assert result.stdout==b'policy-retained\\n' and not result.stderr\n"
        "snapshot.verify();snapshot.close()",
    )


def test_private_gpu_policy_refuses_nonblocking_control_description(tmp_path: Path) -> None:
    admission = _ADMIT.replace(
        "os.set_inheritable(channel.fileno(),False)\n",
        "os.set_inheritable(channel.fileno(),False)\nos.set_blocking(channel.fileno(),False)\n",
    )
    _gpu_run(
        tmp_path,
        "try:\n" + "\n".join(" " + line for line in admission.splitlines()) + "\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Kernel-nonblocking borrowed control description admitted')\n"
        "os.fstat(channel.fileno())",
    )


def test_private_gpu_policy_refuses_changed_control_flags(tmp_path: Path) -> None:
    _gpu_run(
        tmp_path,
        _ADMIT + "os.set_blocking(channel.fileno(),False)\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Changed original kernel control flags admitted')\n"
        "snapshot.close();os.fstat(channel.fileno())",
    )

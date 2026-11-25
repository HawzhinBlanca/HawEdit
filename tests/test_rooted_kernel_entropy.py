"""Real kernel endpoint/custody controls, not model or producer admission."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_linux_snapshot import _run
from test_rooted_linux_image import _rooted_run

_ADMIT = (
    "from hawedit.linux_snapshot import SnapshotMode\n"
    "snapshot=LinuxSnapshot(root,(*runtime_files,"
    "SnapshotFile(source,'input.bin',sha,len(original))),"
    "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True,max_bytes=8388608)\n"
)


def test_rooted_entropy_default_is_absent(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "snapshot=LinuxSnapshot(root,(*runtime_files,"
        "SnapshotFile(source,'input.bin',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE,max_bytes=8388608)\n"
        "assert not Path('/dev/urandom').exists()\n"
        "snapshot.verify();snapshot.close()",
    )


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_rooted_entropy_mode_and_type_refusals(tmp_path: Path, value: object) -> None:
    _run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "try:\n"
        " LinuxSnapshot(root,(SnapshotFile(source,'input.bin',sha,len(original)),),"
        f"mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy={value!r})\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Untyped entropy option admitted')\n"
        "assert not tuple(root.iterdir()) and source.read_bytes()==original",
    )


def test_rooted_entropy_data_only_refuses(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "try:\n"
        " LinuxSnapshot(root,(SnapshotFile(source,'input.bin',sha,len(original)),),"
        "kernel_entropy=True)\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Data-only image exposed a device')\n"
        "assert not tuple(root.iterdir()) and source.read_bytes()==original",
    )


@pytest.mark.parametrize("name", ["dev", "dev/urandom", "dev/urandom/foreign"])
def test_rooted_entropy_declaration_collision_refuses(tmp_path: Path, name: str) -> None:
    _run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "try:\n"
        f" LinuxSnapshot(root,(SnapshotFile(source,{name!r},sha,len(original)),),"
        "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True)\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Declaration replaced reserved entropy path')\n"
        "assert not tuple(root.iterdir()) and source.read_bytes()==original",
    )


def test_rooted_entropy_original_readonly_endpoint(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        _ADMIT + "import fcntl\n"
        "assert snapshot._entropy is not None\n"
        "first,anchor=snapshot._entropy\n"
        "assert fcntl.fcntl(first,1027,anchor)==1\n"
        "for fd in (first,anchor):\n"
        " info=os.fstat(fd);assert stat.S_ISCHR(info.st_mode)\n"
        " assert os.major(info.st_rdev)==1 and os.minor(info.st_rdev)==9\n"
        " assert not os.get_inheritable(fd)\n"
        " assert fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY\n"
        " assert len(os.read(fd,32))==32\n"
        "info=os.stat('/dev/urandom');expected=os.fstat(first)\n"
        "assert (info.st_dev,info.st_ino,info.st_rdev)=="
        "(expected.st_dev,expected.st_ino,expected.st_rdev)\n"
        "flags=os.statvfs('/dev/urandom').f_flag\n"
        "required=os.ST_RDONLY|os.ST_NOSUID|os.ST_NOEXEC\n"
        "assert flags&required==required and not flags&os.ST_NODEV\n"
        "assert os.statvfs('/').f_flag&os.ST_NODEV\n"
        "assert not Path('/dev/null').exists() and not source.exists()\n"
        "assert snapshot.path('input.bin').read_bytes()==original\n"
        "try:snapshot.path('dev/urandom')\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Entropy was misrepresented as copied bytes')\n"
        "try:os.write(first,b'not-written')\n"
        "except OSError as exc:assert exc.errno==errno.EBADF\n"
        "else:raise AssertionError('Readonly original accepted a write')\n"
        "snapshot.verify();snapshot.close()",
    )


@pytest.mark.parametrize("operation", ["open", "openat", "creat", "openat2"])
def test_rooted_entropy_writable_syscalls_refuse(tmp_path: Path, operation: str) -> None:
    calls = {
        "open": "native.syscall(2,path,ctypes.c_int(flags),ctypes.c_int(0o600))",
        "openat": "native.syscall(257,ctypes.c_int(-100),path,"
        "ctypes.c_int(flags),ctypes.c_int(0o600))",
        "creat": "native.syscall(85,path,ctypes.c_int(0o600))",
        "openat2": "native.syscall(437,ctypes.c_int(-100),path,"
        "ctypes.byref(how),ctypes.c_size_t(ctypes.sizeof(how)))",
    }
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "class How(ctypes.Structure):\n"
        " _fields_=[('flags',ctypes.c_uint64),('mode',ctypes.c_uint64),"
        "('resolve',ctypes.c_uint64)]\n"
        "native=ctypes.CDLL(None,use_errno=True);native.syscall.restype=ctypes.c_long\n"
        "path=ctypes.c_char_p(b'/dev/urandom');how=How()\n"
        + _ADMIT
        + "for flags in (os.O_WRONLY,os.O_RDWR,os.O_CREAT,os.O_TRUNC,os.O_APPEND):\n"
        " how.flags=flags;ctypes.set_errno(0)\n"
        f" result={calls[operation]}\n"
        " if result>=0:\n"
        "  os.close(result);raise AssertionError('Writable endpoint open succeeded')\n"
        f" assert ctypes.get_errno()==errno.{'ENOSYS' if operation == 'openat2' else 'EPERM'}\n"
        "for result in (native.syscall(2,path,ctypes.c_int(os.O_RDONLY)),"
        "native.syscall(257,ctypes.c_int(-100),path,ctypes.c_int(os.O_RDONLY))):\n"
        " assert result>=0;assert len(os.read(result,32))==32;os.close(result)\n"
        "ctypes.set_errno(0);assert native.unshare(0x10000000)==-1\n"
        "assert ctypes.get_errno()==errno.EPERM\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_entropy_preexisting_writer_refuses(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "writer=os.open('/dev/urandom',os.O_WRONLY|os.O_CLOEXEC|os.O_NOFOLLOW)\n"
        "try:\n"
        " try:\n"
        "  LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'input.bin',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True,max_bytes=8388608)\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Preexisting entropy writer admitted')\n"
        " assert stat.S_ISCHR(os.fstat(writer).st_mode)\n"
        " assert source.read_bytes()==original and not tuple(root.iterdir())\n"
        "finally:os.close(writer)",
    )


@pytest.mark.parametrize("target", ["original", "anchor", "reopened"])
def test_rooted_entropy_substitution_and_cleanup_refuse(tmp_path: Path, target: str) -> None:
    _rooted_run(
        tmp_path,
        _ADMIT + "assert snapshot._entropy is not None\n"
        "first,anchor=snapshot._entropy\n"
        f"replaced={'anchor' if target == 'anchor' else 'first'}\n"
        f"foreign=os.open({'/dev/urandom' if target == 'reopened' else '/proc/self/status'!r},"
        "os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)\n"
        "identity=os.fstat(foreign)\n"
        "os.dup2(foreign,replaced,inheritable=False);os.close(foreign)\n"
        "try:snapshot.verify()\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Substituted entropy description accepted')\n"
        "snapshot.close()\n"
        "assert (os.fstat(replaced).st_dev,os.fstat(replaced).st_ino)=="
        "(identity.st_dev,identity.st_ino)\n"
        "os.close(replaced)",
    )


def test_rooted_entropy_kernel_mount_refusal(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "from hawedit.linux_snapshot import SnapshotMode,_Filter,_Program\n"
        "native=LinuxSnapshot._libc()\n"
        "rules=(_Filter*6)(_Filter(0x20,0,0,0),_Filter(0x15,0,3,165),"
        "_Filter(0x20,0,0,40),_Filter(0x15,0,1,4096),"
        "_Filter(0x06,0,0,0x50000|errno.EPERM),_Filter(0x06,0,0,0x7fff0000))\n"
        "program=_Program(len(rules),rules)\n"
        "assert native.prctl(22,2,ctypes.addressof(program),0,0)==0\n"
        "try:\n"
        " LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'input.bin',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True,max_bytes=8388608)\n"
        "except LinuxSnapshotError as exc:\n"
        " assert isinstance(exc.__cause__,OSError) and exc.__cause__.errno==errno.EPERM\n"
        "else:raise AssertionError('Kernel-denied endpoint mount was admitted')\n"
        "try:\n"
        " LinuxSnapshot(root,tuple(runtime_files),mode=SnapshotMode.ROOTED_IMAGE)\n"
        "except LinuxSnapshotError:pass\n"
        "else:raise AssertionError('Failed initializer retried in the same process')",
    )


def test_rooted_entropy_actual_copied_python_consumer(tmp_path: Path) -> None:
    consumer = (
        "import json,os\n"
        "from pathlib import Path\n"
        "assert os.getcwd()=='/'\n"
        "with open('/dev/urandom','rb') as stream:assert len(stream.read(32))==32\n"
        "assert json.loads(Path('/models/config.json').read_text())=={'num_beams':1}\n"
        "for row in Path('/proc/self/maps').read_text().splitlines():\n"
        " fields=row.split(maxsplit=5)\n"
        " if len(fields)!=6 or not fields[5].startswith('/'):continue\n"
        " info=os.stat(fields[5]);major,minor=fields[3].split(':')\n"
        " assert os.makedev(int(major,16),int(minor,16))==info.st_dev\n"
        " assert int(fields[4])==info.st_ino\n"
        "print('private-config-and-kernel-entropy')\n"
    )
    _rooted_run(
        tmp_path,
        "import subprocess,sysconfig\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
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
        "configuration=source.parent/'generation_config.json'\n"
        "configuration.write_bytes(b'{\"num_beams\":1}\\n')\n"
        "declare(configuration,'models/config.json')\n"
        "assert len(files)<=6000 and sum(item.size_bytes for item in files)<=512*1024**2\n"
        "snapshot=LinuxSnapshot(root,tuple(files),mode=SnapshotMode.ROOTED_IMAGE,"
        "kernel_entropy=True,max_bytes=512*1024**2,max_files=6000)\n"
        "channel.send(b'copy-ready');assert channel.recv(32)==b'continue'\n"
        f"result=subprocess.run([str(executable),'-I','-B','-c',{consumer!r}],"
        "capture_output=True,timeout=3,check=False)\n"
        "assert result.returncode==0,result.stderr\n"
        "assert result.stdout==b'private-config-and-kernel-entropy\\n'\n"
        "assert not configuration.exists() and not source.exists()\n"
        "snapshot.verify();snapshot.close()",
        parent="assert select.select([left],[],[],8)[0]\n"
        "packet=left.recv(65536);assert packet==b'copy-ready',packet\n"
        "configuration=base/'generation_config.json'\n"
        "configuration.rename(base/'original-config.json')\n"
        "configuration.write_bytes(b'{\"num_beams\":2}\\n')\n"
        "left.send(b'continue')",
    )


def test_rooted_entropy_async_open_syscalls_refuse(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "native=ctypes.CDLL(None,use_errno=True);native.syscall.restype=ctypes.c_long\n"
        "parameters=ctypes.create_string_buffer(256)\n" + _ADMIT + "for number in (425,426,427):\n"
        " ctypes.set_errno(0)\n"
        " result=native.syscall(number,ctypes.c_int(2),ctypes.byref(parameters),0,0,0,0)\n"
        " if result>=0:\n"
        "  os.close(result);raise AssertionError('Async file-open entry admitted')\n"
        " assert ctypes.get_errno()==errno.ENOSYS\n"
        "snapshot.verify();snapshot.close()",
    )


def test_rooted_entropy_preexisting_ring_refuses(tmp_path: Path) -> None:
    _rooted_run(
        tmp_path,
        "import ctypes\n"
        "from hawedit.linux_snapshot import SnapshotMode\n"
        "native=ctypes.CDLL(None,use_errno=True);native.syscall.restype=ctypes.c_long\n"
        "parameters=ctypes.create_string_buffer(256)\n"
        "ring=native.syscall(425,ctypes.c_uint(2),ctypes.byref(parameters))\n"
        "assert ring>=0,ctypes.get_errno()\n"
        "try:\n"
        " assert os.readlink('/proc/self/fd/'+str(ring))=='anon_inode:[io_uring]'\n"
        " try:\n"
        "  LinuxSnapshot(root,(*runtime_files,SnapshotFile(source,'input.bin',sha,len(original))),"
        "mode=SnapshotMode.ROOTED_IMAGE,kernel_entropy=True,max_bytes=8388608)\n"
        " except LinuxSnapshotError:pass\n"
        " else:raise AssertionError('Retained asynchronous ring admitted')\n"
        " assert os.readlink('/proc/self/fd/'+str(ring))=='anon_inode:[io_uring]'\n"
        " assert source.read_bytes()==original and not tuple(root.iterdir())\n"
        "finally:os.close(ring)",
    )

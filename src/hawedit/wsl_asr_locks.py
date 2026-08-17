"""Reviewed hash locks for the isolated Linux/CPython 3.12 OmniASR runtime.

Generated with uv 0.11.26 against the default https://pypi.org/simple index on 2026-08-09:
``uv pip compile pyproject.toml --extra asr --python-version 3.12 --python-platform
x86_64-manylinux_2_28 --generate-hashes --no-header --no-annotate --exclude-newer
2026-08-09T10:22:16Z``. A PyPI JSON pass retained only the most-preferred compatible target
artifact per distribution. Runtime installation is binary-only except for the explicitly named
upstream sdist-only projects.

The hashes bind downloaded wheels/sdists and the receipt binds the complete installed
name/version set. They do not make a mutable venv immutable, attest locally compiled bytes,
or bind the WSL compiler, system headers, uv executable, or Python patch-level installer.
"""

from __future__ import annotations

import hashlib
import re
from types import MappingProxyType
from typing import Final

SDIST_EXCEPTIONS: Final = ("kenlm", "sox")

BUILD_REQUIREMENTS: Final = r"""cmake==4.4.2 \
    --hash=sha256:27b024e903ef985b37183d754a5c61230b56b41fe0971cd44b71b80c787ec594
pip==26.2.1 \
    --hash=sha256:71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e
setuptools==84.0.0 \
    --hash=sha256:51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670
wheel==0.47.0 \
    --hash=sha256:212281cab4dff978f6cedd499cd893e1f620791ca6ff7107cf270781e587eced"""
RUNTIME_REQUIREMENTS: Final = r"""accelerate==1.12.0 \
    --hash=sha256:3e2091cd341423207e2f084a6654b1efcd250dc326f2a37d6dde446e07cabb11
annotated-doc==0.0.5 \
    --hash=sha256:117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101
annotated-types==0.8.0 \
    --hash=sha256:f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0
anyio==4.14.2 \
    --hash=sha256:9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494
audioread==3.1.0 \
    --hash=sha256:b30d1df6c5d3de5dcef0fb0e256f6ea17bdcf5f979408df0297d8a408e2971b4
av==18.0.0 \
    --hash=sha256:ae56b40b6f8b067a8ad2dac664fbfbabac7f7a55b9a7bb031eb99289252bc017
blinker==1.9.0 \
    --hash=sha256:ba0efaa9080b619ff2f3459d1d500c57bddea4a6b424b60a91141db6fd2f08bc
blobfile==3.0.0 \
    --hash=sha256:48ecc3307e622804bd8fe13bf6f40e6463c4439eba7a1f9ad49fd78aa63cc658
brotli==1.2.0 \
    --hash=sha256:072e7624b1fc4d601036ab3f4f27942ef772887e876beff0301d261210bca97f
certifi==2026.7.22 \
    --hash=sha256:62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775
cffi==2.1.1 \
    --hash=sha256:c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf
charset-normalizer==3.4.9 \
    --hash=sha256:5e226f6218febc71f6c1fc2fafb91c226f75bdc1d8fb12d66823716e891608fd
chunspell==2.0.4 \
    --hash=sha256:1632bfa913f6c91f6fe90685e28ca98ba27472471153c81adb2a6de6e5ea5212
click==8.4.2 \
    --hash=sha256:e6f9f66136c816745b9d65817da91d61d957fb16e02e4dcd0552553c5a197b76
colorama==0.4.6 \
    --hash=sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6
cython==3.2.9 \
    --hash=sha256:23e80bc885c599e72072e18d0746df82d394b73100c1e153cda7359e6e59fe09
decorator==5.3.1 \
    --hash=sha256:f47fe6fdbd2edd623ecfe36875d37aba411624e2670dd395dddae1358689bb3c
dynet38==2.2 \
    --hash=sha256:8693bf8e98fdddfa116fa1e213f1c471be772e1b9e006ad5278a2b2a8f7b4d70
editdistance==0.8.1 \
    --hash=sha256:c59248eabfad603f0fba47b0c263d5dc728fb01c2b6b50fb6ca187cec547fdb3
fairseq2==0.6 \
    --hash=sha256:c83c19fe74b020d4404f0bfb7a0ebb681148545f3195a46e27c2e54f74d745c5
fairseq2n==0.6 \
    --hash=sha256:9ade57197a6c3ae7ab72259c0a2df4432980c5a02cd066c235dd88d4869c2fdf
fastapi==0.141.1 \
    --hash=sha256:bfb91aa2d334c61cb35ba9a116fc123b3d3df31640b801cf57a7a78ec3f603b3
filelock==3.32.2 \
    --hash=sha256:87dd94cf281e586d135fa51132b8e3d9a598b316e90377a288663c9321036c82
flask==3.1.3 \
    --hash=sha256:f4bcbefc124291925f1a26446da31a5178f9483862233b23c0c96a20701f670c
fonttools==4.60.2 \
    --hash=sha256:98d0719f1b11c2817307d2da2e94296a3b2a3503f8d6252a101dca3ee663b917
fsspec==2026.7.0 \
    --hash=sha256:b57ddbafedfaef7018c1ecab32aa200a9d7ca26b77965f64e48b70061249d279
gradio==6.17.3 \
    --hash=sha256:7e52c65bfbb7bd75ac1c28cb38f93b01e5f6a2ff013224e6213533451bfee517
gradio-client==2.5.0 \
    --hash=sha256:d43e2179c29076292a76485ad7ed2e6eaa19d14ac58283bd7f5beabfe4ca958c
groovy==0.1.2 \
    --hash=sha256:7f7975bab18c729a257a8b1ae9dcd70b7cafb1720481beae47719af57c35fa64
h11==0.16.0 \
    --hash=sha256:63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86
hf-gradio==0.4.1 \
    --hash=sha256:76b8cb8be6abe62d74c1ad2d35b42f0629db89aa9e1a8d033cecfe7c856eeab3
hf-xet==1.6.0 \
    --hash=sha256:d62671bb130879cef0ee4c9ebe47a14af6c66ec53e6d84dc15936e5ffdfac82f
httpcore==1.0.9 \
    --hash=sha256:2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55
httpx==0.28.1 \
    --hash=sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad
huggingface-hub==0.36.2 \
    --hash=sha256:48f0c8eac16145dfce371e9d2d7772854a4f591bcb56c9cf548accf531d54270
idna==3.18 \
    --hash=sha256:7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2
importlib-metadata==7.2.1 \
    --hash=sha256:ffef94b0b66046dd8ea2d619b701fe978d9264d38f3998bc4c27ec3b146a87c8
importlib-resources==6.5.2 \
    --hash=sha256:789cfdc3ed28c78b67a06acb8126751ced69a3d5f79c095a98298cd8a760ccec
itsdangerous==2.2.0 \
    --hash=sha256:c6242fc49e35958c8b15141343aa660db5fc54d4f13a1db01a3f5891b98700ef
jinja2==3.1.6 \
    --hash=sha256:85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67
joblib==1.5.3 \
    --hash=sha256:5fc3c5039fc5ca8c0276333a188bbd59d6b7ab37fe6632daa76bc7f9ec18e713
kenlm==0.3.0 \
    --hash=sha256:c4628bb9fb63c8a6f9240035b8b037385cfc404cb72e933cf48878291edac1e8
klpt==0.1.7 \
    --hash=sha256:4109c56128fd9af478881c3516cc28106b593dae2ccdf769d1c1d361be00749d
lazy-loader==0.5 \
    --hash=sha256:ab0ea149e9c554d4ffeeb21105ac60bed7f3b4fd69b1d2360a4add51b170b005
librosa==0.11.0 \
    --hash=sha256:0b6415c4fd68bff4c29288abe67c6d80b587e0e1e2cfb0aad23e4559504a7fa1
llvmlite==0.48.0 \
    --hash=sha256:416fa4c2c66c2c6dc6d0a402648c19206e548efa0aa1eff01ad5cdad0af8217d
lxml==6.1.1 \
    --hash=sha256:ebe6af670449830d6d9b752c256a983291c766a1365ba5d5460048f9e33a7818
markdown-it-py==4.2.0 \
    --hash=sha256:9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a
markupsafe==3.0.3 \
    --hash=sha256:d6dd0be5b5b189d31db7cda48b91d7e0a9795f31430b7f271219ab30f1d3ac9d
mdurl==0.1.2 \
    --hash=sha256:84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8
mpmath==1.3.0 \
    --hash=sha256:a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c
msgpack==1.2.1 \
    --hash=sha256:020e881a764b20d8d7ca1a54fc01b8175519d108e3c3f194fddc200bda95951a
mypy-extensions==1.1.0 \
    --hash=sha256:1be4cccdb0f2482337c4743e60421de3a356cd97508abadd57d47403e94f5505
nagisa==0.2.11 \
    --hash=sha256:43f2a5a30aa4b5c3f9018062e4c892efb6c18ae80f0d67a9a0611aa3d260dc37
narwhals==2.24.0 \
    --hash=sha256:42fdedf44e5b2ca7505630d45b4ac3058f38d8485cba9fe1652ca23152df7489
networkx==3.6.1 \
    --hash=sha256:d47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762
numba==0.66.0 \
    --hash=sha256:0999e3ee1b18c48e1fb51d11af35ef59852c7f4f50569c9550c25faef0616ad1
numpy==1.26.4 \
    --hash=sha256:675d61ffbfa78604709862923189bad94014bef562cc35cf61d3a07bba02a7ed
nvidia-cublas-cu12==12.8.4.1 \
    --hash=sha256:8ac4e771d5a348c551b2a426eda6193c19aa630236b418086020df5ba9667142
nvidia-cuda-cupti-cu12==12.8.90 \
    --hash=sha256:ea0cb07ebda26bb9b29ba82cda34849e73c166c18162d3913575b0c9db9a6182
nvidia-cuda-nvrtc-cu12==12.8.93 \
    --hash=sha256:a7756528852ef889772a84c6cd89d41dfa74667e24cca16bb31f8f061e3e9994
nvidia-cuda-runtime-cu12==12.8.90 \
    --hash=sha256:adade8dcbd0edf427b7204d480d6066d33902cab2a4707dcfc48a2d0fd44ab90
nvidia-cudnn-cu12==9.10.2.21 \
    --hash=sha256:949452be657fa16687d0930933f032835951ef0892b37d2d53824d1a84dc97a8
nvidia-cufft-cu12==11.3.3.83 \
    --hash=sha256:4d2dd21ec0b88cf61b62e6b43564355e5222e4a3fb394cac0db101f2dd0d4f74
nvidia-cufile-cu12==1.13.1.3 \
    --hash=sha256:1d069003be650e131b21c932ec3d8969c1715379251f8d23a1860554b1cb24fc
nvidia-curand-cu12==10.3.9.90 \
    --hash=sha256:b32331d4f4df5d6eefa0554c565b626c7216f87a06a4f56fab27c3b68a830ec9
nvidia-cusolver-cu12==11.7.3.90 \
    --hash=sha256:4376c11ad263152bd50ea295c05370360776f8c3427b30991df774f9fb26c450
nvidia-cusparse-cu12==12.5.8.93 \
    --hash=sha256:1ec05d76bbbd8b61b06a80e1eaf8cf4959c3d4ce8e711b65ebd0443bb0ebb13b
nvidia-cusparselt-cu12==0.7.1 \
    --hash=sha256:f1bb701d6b930d5a7cea44c19ceb973311500847f81b634d802b7b539dc55623
nvidia-nccl-cu12==2.27.3 \
    --hash=sha256:adf27ccf4238253e0b826bce3ff5fa532d65fc42322c8bfdfaf28024c0fbe039
nvidia-nvjitlink-cu12==12.8.93 \
    --hash=sha256:81ff63371a7ebd6e6451970684f916be2eab07321b73c9d244dc2b4da7f73b88
nvidia-nvtx-cu12==12.8.90 \
    --hash=sha256:5b17e2001cc0d751a5bc2c6ec6d26ad95913324a4adb86788c944f8ce9ba441f
omnilingual-asr==0.2.0 \
    --hash=sha256:6b8e811143603463c371c23464ff1946a52f876e6b6a62c5fb3deee6e39ab6d4
orjson==3.11.9 \
    --hash=sha256:be4fa4f0af7fa18951f7ab3fc2148e223af211bf03f59e1c6034ec3f97f21d61
packaging==24.2 \
    --hash=sha256:09abb1bccd265c01f4a3aa3f7a7db064b36514d2cba19a2f694fe6150451a759
pandas==3.0.5 \
    --hash=sha256:d373ce03ffd84010ed9839fa73672a9c8256990532e158440c0085db7d914b34
pillow==12.3.0 \
    --hash=sha256:78cb2c6865a35ab8ff8b75fd122f6033b92a62c82801110e48ddd6c936a45d91
platformdirs==4.11.1 \
    --hash=sha256:2efd27d363e8dd2e661639ffb398865a5e0a46442a11d266bf375a0e0c10e386
polars==1.43.2 \
    --hash=sha256:22aa0cb92a1ee2d60d6a15a638b2e8e0dd99aea21ac0cd8fb29da8e382e075a9
polars-runtime-32==1.43.2 \
    --hash=sha256:6d5a7ae004a2723ebf4427f6d6a639f30f86af4cf077075f6b35d04711154fc3
pooch==1.9.0 \
    --hash=sha256:f265597baa9f760d25ceb29d0beb8186c243d6607b0f60b83ecf14078dbc703b
portalocker==4.1.0 \
    --hash=sha256:d985a430d265adf31adf12bc0bf3501aea59efc495e9104c057e5dfb7394c226
psutil==5.9.8 \
    --hash=sha256:d06016f7f8625a1825ba3732081d77c94589dca78b7a3fc072194851e88461a4
pyarrow==25.0.0 \
    --hash=sha256:5d1dbf24e151042f2fa3c129563f65d66674128868496fb008c4272b16bdf778
pycparser==3.0 \
    --hash=sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992
pycryptodomex==3.23.0 \
    --hash=sha256:f489c4765093fb60e2edafdf223397bc716491b2b69fe74367b70d6999257a5c
pydantic==2.13.4 \
    --hash=sha256:45a282cde31d808236fd7ea9d919b128653c8b38b393d1c4ab335c62924d9aba
pydantic-core==2.46.4 \
    --hash=sha256:926c9541b14b12b1681dca8a0b75feb510b06c6341b70a8e500c2fdcff837cce
pydub==0.25.1 \
    --hash=sha256:65617e33033874b59d87db603aa1ed450633288aefead953b30bded59cb599a6
pygments==2.20.0 \
    --hash=sha256:81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176
python-dateutil==2.9.0.post0 \
    --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427
python-multipart==0.0.32 \
    --hash=sha256:ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23
pytz==2026.3.post1 \
    --hash=sha256:dd95840dd199baea12d9cc096a1d452caa6596a1c1e4b5f3dbd1541855d5e815
pyyaml==6.0.3 \
    --hash=sha256:ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc
qwen-asr==0.0.6 \
    --hash=sha256:b9c55a38413298f3a990a4475467399daec6e8f4172363053fc42e2166c2dfd3
qwen-omni-utils==0.0.9 \
    --hash=sha256:f111db07af669c83333411c5177131e18e831fe666d6a55a1af263952ada8939
regex==2026.7.19 \
    --hash=sha256:9dce8ec9695f531a1b8a6f314fd4b393adcccf2ea861db480cdf97a301d01a68
requests==2.34.2 \
    --hash=sha256:2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0
retrying==1.3.7 \
    --hash=sha256:4449b0a9f6754ab381aabc2771a2aa8350cfe194c2238992e1303b662cfa94e2
rich==13.9.4 \
    --hash=sha256:6049d5e6ec054bf2779ab3358186963bac2ea89175919d699e378b99738c2a90
ruamel-yaml==0.19.1 \
    --hash=sha256:27592957fedf6e0b62f281e96effd28043345e0e66001f97683aa9a40c667c93
sacrebleu==2.6.0 \
    --hash=sha256:3edc1531575cfe4ad04ce53491a9307e234af1c3f805a1f491cbec844229a8a8
safehttpx==0.1.7 \
    --hash=sha256:c4f4a162db6993464d7ca3d7cc4af0ffc6515a606dfd220b9f82c6945d869cde
safetensors==0.8.0 \
    --hash=sha256:fd6f3f93c9a0a7cc2788ee63fb763353d4bd2e89b0751bc78fcf7dda00bea774
scikit-learn==1.9.0 \
    --hash=sha256:056c92bb67ad4c28463c2f2653d9701449201e7e7a9e94e321be0f71c4fef2b8
scipy==1.17.1 \
    --hash=sha256:02ae3b274fde71c5e92ac4d54bc06c42d80e399fec704383dcd99b301df37458
semantic-version==2.10.0 \
    --hash=sha256:de78a3b8e0feda74cabc54aab2da702113e33ac9d9eb9d2389bcf1f58b7d9177
setuptools==84.0.0 \
    --hash=sha256:51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670
shellingham==1.5.4 \
    --hash=sha256:7ecfff8f2fd72616f7481040475a65b2bf8af90a56c89140852d1120324e8686
six==1.17.0 \
    --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274
soundfile==0.14.0 \
    --hash=sha256:1e38bac1853412871318e82a1ba69a8be677619b56025bbfcccdb41b6cafe82d
sox==1.5.0 \
    --hash=sha256:12c7be5bb1f548d891fe11e82c08cf5f1a1d74e225298f60082e5aeb2469ada0
soxr==1.1.0 \
    --hash=sha256:3b033078e86f3c4a658e5697fac8995764fad9e799563616b630136b613167f1
soynlp==0.0.493 \
    --hash=sha256:2aed0ced1f0f74f7bdd0bdc24a979c5cb9ee4a28393642db52a83d174ed65b7a
starlette==1.6.0 \
    --hash=sha256:a86dd39d14bb45f85a3d18525215a9ef0cfd1f192ac793220e72598c90335f0c
sympy==1.14.0 \
    --hash=sha256:e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5
tabulate==0.10.0 \
    --hash=sha256:f0b0622e567335c8fabaaa659f1b33bcb6ddfe2e496071b743aa113f8774f2d3
tbb==2023.1.0 \
    --hash=sha256:64ad35241c736a595498f5343abec8eaaa203e9fe0dbdbf4b86d37c5a3ab1d9c
tcmlib==1.5.0 \
    --hash=sha256:9d7c01cff35aae9bf5390b620680ebdf10a7d211c22d6488a27a029502e7d0aa
threadpoolctl==3.6.0 \
    --hash=sha256:43a0b8fd5a2928500110039e43a5eed8480b918967083ea48dc3ab9f13c4a7fb
tiktoken==0.13.0 \
    --hash=sha256:a116178fa7e1b4065bff05214360373a65cac22f965be7b3f73d00a0dbfe7649
tokenizers==0.22.2 \
    --hash=sha256:369cc9fc8cc10cb24143873a0d95438bb8ee257bb80c71989e3ee290e8d72c67
tomlkit==0.14.0 \
    --hash=sha256:592064ed85b40fa213469f81ac584f67a4f2992509a7c3ea2d632208623a3680
torch==2.8.0 \
    --hash=sha256:b2aca0939fb7e4d842561febbd4ffda67a8e958ff725c1c27e244e85e982173c
torchaudio==2.8.0 \
    --hash=sha256:93a8583f280fe83ba021aa713319381ea71362cc87b67ee38e97a43cb2254aee
torcheval==0.0.7 \
    --hash=sha256:20cc34dac7aa9b32f942c8a9f014d1d02098631b6cd0b102c078600577017956
tqdm==4.70.0 \
    --hash=sha256:7f585706bfddbdebf89daac705b2dfcc16890130727d3197ca62c732b4310953
transformers==4.57.6 \
    --hash=sha256:4c9e9de11333ddfe5114bc872c9f370509198acf0b87a832a0ab9458e2bd0550
triton==3.4.0 \
    --hash=sha256:31c1d84a5c0ec2c0f8e8a072d7fd150cab84a9c239eaddc6706c081bfae4eb04
typer==0.27.1 \
    --hash=sha256:53150287edd11baeb4e4722c8e394fcdf8181c0ae89485cba8d25c778d5edd56
typing-extensions==4.16.0 \
    --hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8
typing-inspection==0.4.2 \
    --hash=sha256:4ed1cacbdc298c220f1bd249ed5287caa16f34d44ef4e9c3d0cbad5b521545e7
urllib3==2.7.0 \
    --hash=sha256:9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897
uvicorn==0.52.1 \
    --hash=sha256:e4403f9d93188cf9d1088e9f40e3acd12630e2df8675316704379a7fc20fff6a
werkzeug==3.1.8 \
    --hash=sha256:63a77fb8892bf28ebc3178683445222aa500e48ebad5ec77b0ad80f8726b1f50
xxhash==3.8.1 \
    --hash=sha256:82c0cedd280eab2e8291270e6c04894dbc096f8159a39dcf1807429f026ca3cc
zipp==4.1.0 \
    --hash=sha256:25ad4e16390cd314347dd8f1de67a2ac538ae658ed4ab9db16029c07c188e97f"""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _versions(*locks: str) -> MappingProxyType[str, str]:
    versions: dict[str, str] = {}
    for lock in locks:
        for name, version in re.findall(r"(?m)^([a-z0-9-]+)==([^\s\\]+)", lock):
            previous = versions.setdefault(name, version)
            if previous != version:
                raise RuntimeError(f"conflicting WSL ASR lock for {name}: {previous}/{version}")
    return MappingProxyType(dict(sorted(versions.items())))


BUILD_LOCK_SHA256: Final = _sha256(BUILD_REQUIREMENTS)
RUNTIME_LOCK_SHA256: Final = _sha256(RUNTIME_REQUIREMENTS)
LOCKED_DISTRIBUTIONS: Final = _versions(BUILD_REQUIREMENTS, RUNTIME_REQUIREMENTS)

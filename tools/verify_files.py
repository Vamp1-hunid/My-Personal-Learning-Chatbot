r"""verify_files.py - checks that every QuantaKai source file is exactly right.

Run from the QuantaKai folder:   runtime\python\python.exe tools\verify_files.py
Each file's SHA-256 fingerprint is compared with the one in the build guide.
Windows line endings (CRLF) and plain ones (LF) count as the same.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {
    "config.json": "0eae207bcab3e6eaa199e5b140e043aed8152a6d616c5f6a4bcd90c1049f9af8",
    "requirements.txt": "414f04b96d211d54b294437dba8742e5742aa43b60c26cf3818b3aef57dbe094",
    "app/__init__.py": "70df3555e9c095fa128e9890e5098221a4031dd208fa5acc16db74cd1ae355ff",
    "app/settings.py": "c389f95d0fd8027924b66fc838afc63981f57054c592cf051c5c4a27bf7576dc",
    "app/prompts.py": "b66c8f35126a10e035f9b2f45fc2abe414147c656fb6cf53ac6dbc3c4deee1f0",
    "app/engine.py": "30ce8c9b67ca298c8e9da99bb19edd5f59d833cfc842c9f4b782115c155524f2",
    "app/llm.py": "ef91433dfbaba37b19885f6c59dc86076b2f781a46fb7eb94028722e692322bd",
    "app/library.py": "0734f1c12a656cac7e3eaccf7bb0b5fe44d644966de6878bc756bd098313bbfd",
    "app/memory.py": "f07c6c67a12b5aff86fb1ccd0b46fb433022281b075a2f80b35e5cd58e655354",
    "app/web.py": "5300fc142cf16039aea1e2a2c78a0266ce9d20a27cbe4c4035e73b85066ec9b9",
    "app/runner.py": "bd9a081876cbabb173a2c01ae2d2b32bda5ff77879f167778c46669ca0d27e07",
    "app/ocr.py": "054d5718d45ee062ca6010257c1f07f32a5a91b69eebfb2fdeaa754d042c3614",
    "app/docs.py": "eaa6d0f8da0f8cf26dcb660e0f2fdd5f1522e7f1c63bf10922ed2a92bbd9b251",
    "app/organize.py": "bb229879c41735bd623cb5c8c7302516cd8cbe1fb6122743685983eb40d6f9bf",
    "app/kokoro_worker.py": "c9da9aea890628041b37900b9ff948bd77978dd9dcd38aea6c22f3bd402c0fbd",
    "app/voice.py": "9ef531c2a48f09b7acdf23386196825a3a8c5e711642ac05473e3199f9d25469",
    "app/chat.py": "674c4f1f84c9358115ed577d1a00d6ecdbac95276a87f88cc313bbe49447a4bc",
    "app/server.py": "f9b7a1bf3b2adda1d3a5defa0781142c322213d736e78b1e43d44fbd2c70f2d5",
    "app/stop.py": "b8da98201c3e62fdc662f67f717861108a34b6ef0b9529b7b83747c991ffb6bc",
    "ui/index.html": "103fd410c1ef3956ad86a09861f56890deab4d5794f34c1e6e1e718a2a872987",
    "START.bat": "ffdc2b18a5634c7a76344d3e5a29d3622988f2f89fa61bdccc7a966ef600bf70",
    "STOP.bat": "c7b5417e9473c307fc18169fb39d160a6caee7a836a2652d0a88e37f6ada6afe",
    "SETUP.bat": "a925e8c23b88f9e3bedbb43009e95b6c9736217f4986e7af252d816b89db65bf",
    "VOICE_SETUP.bat": "ca3198f7dfa03ab1fa22035fbe7e7cfe8e1c8a9cf2484ff28859305f67c12cc1",
    "scripts/setup.ps1": "6b9eff55fe0289ce3c9648795c5fb863940877e30b267e3724524943e4b8c65f",
    "scripts/setup_voice.ps1": "ee563bd6b87b68a1911d33a6fec64ddec2191d5591a3363543ea3f1c0bdac8ea",
    "README.txt": "79470198b07512d4bafb77ec4df57be1149edb234428c42353bea8c1ba15508a",
    "tests/fake_llama_server.py": "f5057c38e36e8f5d329e871ea9a67cc4734265f0178a688de7504ad13a435d33",
    "tests/smoke_test.py": "e39aa27ea24040803e649ef58d229126c348281b8fd3f754c5852af704caf690",
}


def fingerprint(path: Path) -> str:
    text = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


bad = 0
for rel, want in EXPECTED.items():
    p = ROOT / rel
    if not p.exists():
        print(f"MISSING    {rel}")
        bad += 1
    elif fingerprint(p) != want:
        print(f"DIFFERENT  {rel}  (copy it again from the guide)")
        bad += 1
    else:
        print(f"OK         {rel}")
print()
print("ALL FILES MATCH" if not bad else f"{bad} file(s) need fixing")
sys.exit(1 if bad else 0)

#!/usr/bin/env python3
"""Install the Oodle decoder used to read PBZ saves (works on Windows, macOS, Linux).

Downloads the prebuilt oozextract 0.5.7 WASM (MIT) that the open-source SaveSmith
project ships, checks SHA-256 of both files, and installs them to
~/.cache/pbz-save-rescue/oozextract (or $PBZ_OOZ_DIR).
This downloads third-party code: ask the user before running it. Needs Node.js to use.
"""
import hashlib, os, shutil, sys, urllib.request

BASE = "https://raw.githubusercontent.com/gundamff/SaveSmith/main/src/games/phantom-blade-zero/codec/oodle/oozextract/"
FILES = {
    "oozextract_bg.wasm": "a4207524a1edee6a67bd8fb3707011adb32a244595149d3ddf86fddedbc32a94",
    "oozextract.js": "2ca8bca1a63e7ad41b4b3c9fe919c81ece3b696f2d14fc68838f75ff6c9e012c",
}
DEST = os.environ.get("PBZ_OOZ_DIR") or os.path.expanduser("~/.cache/pbz-save-rescue/oozextract")


def main():
    if not shutil.which("node"):
        print("提示：还没装 Node.js（https://nodejs.org ，选 LTS）。解压器装好了也要有 Node.js 才能运行。")
    got = {}
    for name, want in FILES.items():
        data = urllib.request.urlopen(BASE + name, timeout=60).read()
        h = hashlib.sha256(data).hexdigest()
        if h != want:
            sys.exit(f"{name} 的 SHA-256 不符（{h}），拒绝安装。上游可能更新了，需要人工核对。")
        got[name] = data
    os.makedirs(DEST, exist_ok=True)
    for name, data in got.items():
        open(os.path.join(DEST, name), "wb").write(data)
    print(f"installed Oodle decoder to {DEST}")


if __name__ == "__main__":
    main()

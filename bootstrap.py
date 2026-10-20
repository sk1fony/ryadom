"""Create a separate environment on first run, then launch Ryadom."""

import os
from pathlib import Path
import platform
import subprocess
import sys
import venv


def main():
    if sys.version_info < (3, 10):
        print("Нужен Python 3.10 или новее: https://www.python.org/downloads/")
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parent
    env = root / (".venv-" + platform.system().lower() + "-" + platform.machine().lower())
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(env)
        check = subprocess.run([str(python), "-c", "import importlib.metadata; assert importlib.metadata.version('qrcode') == '8.2'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "-r", str(root / "requirements.txt")], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print("Не удалось подготовить запуск. Проверьте интернет и установку Python")
        print(str(error))
        return 1
    os.execv(str(python), [str(python), "-u", str(root / "ryadom.py"), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nЗапуск отменён")

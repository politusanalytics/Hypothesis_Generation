"""Enter an ngrok token locally, with hidden input and no token in shell history."""
import getpass
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local-clickhouse"


def main():
    executable = PRIVATE / "tools" / "ngrok" / "ngrok.exe"
    if not executable.is_file():
        print("The local ngrok executable is missing.", file=sys.stderr)
        return 1
    if not sys.stdin.isatty():
        print("Run this command in your own interactive terminal for hidden token entry.", file=sys.stderr)
        return 1
    token = getpass.getpass("Paste your ngrok authtoken (input hidden): ").strip()
    if not token:
        print("No token supplied.", file=sys.stderr)
        return 1
    result = subprocess.run([str(executable), "config", "add-authtoken", token,
                             "--config", str(PRIVATE / "ngrok.yml")],
                            capture_output=True, text=True, timeout=30)
    token = ""
    if result.returncode:
        print(f"ngrok configuration failed (exit {result.returncode}).", file=sys.stderr)
        return 1
    print("ngrok token saved in the ignored private folder. Authentication will be verified when the tunnel starts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

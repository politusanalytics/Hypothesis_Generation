"""Redact historical application logs in-place without displaying their content."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logger import redact_text, _SAFE_FIELDS


def mask_line(line):
    base, separator, raw = line.partition(" | EXTRA: ")
    if not separator:
        # Historical multiline payloads/tracebacks cannot be classified reliably.
        return "[REDACTED historical unstructured log]\n"
    try:
        fields = json.loads(raw)
    except ValueError:
        return "[REDACTED historical malformed log]\n"
    event = fields.get("event_type")
    fields = {key: value for key, value in fields.items() if key in _SAFE_FIELDS}
    fields = {key: redact_text(value) if isinstance(value, str) else value for key, value in fields.items()}
    # Keep the timestamp/level while removing any old message payload.
    prefix = re.match(r"^(.*? - (?:INFO|ERROR|WARNING|DEBUG|CRITICAL) - )", base)
    base = (prefix.group(1) if prefix else "") + "Historical event redacted"
    return base + " | EXTRA: " + json.dumps(fields, ensure_ascii=False) + "\n"


def mask_existing_logs():
    directory = (Path(__file__).resolve().parents[1] / "logs").resolve()
    count = 0
    for path in directory.glob("app.log*"):
        if path.is_file() and path.resolve().parent == directory:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines(True)
            path.write_text("".join(mask_line(line) for line in lines), encoding="utf-8")
            count += 1
    return count


if __name__ == "__main__":
    print(f"{mask_existing_logs()} log file(s) masked.")

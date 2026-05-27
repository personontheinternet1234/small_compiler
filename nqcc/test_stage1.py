#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
COMPILER = ROOT / "nqcc_stage1.py"

VALID = {
    "return_0.c": ("int main() { return 0; }", 0),
    "return_2.c": ("int main() { return 2; }", 2),
    "return_42.c": ("int main(){return 42;}", 42),
    "return_255.c": ("int main() {\n    return 255;\n}", 255),
}

INVALID = {
    "missing_semicolon.c": "int main() { return 2 }",
    "wrong_keyword.c": "int main() { retur 2; }",
    "missing_close_brace.c": "int main() { return 2;",
    "extra_tokens.c": "int main() { return 2; } int main() { return 3; }",
    "negative_number.c": "int main() { return -2; }",
}


def run(cmd, **kwargs):
    return subprocess.run(cmd, text=True, capture_output=True, **kwargs)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        for name, (source, expected) in VALID.items():
            path = tmp / name
            path.write_text(source)
            result = run([sys.executable, str(COMPILER), str(path)])
            if result.returncode != 0:
                print(f"FAIL: compiler rejected valid {name}\n{result.stderr}")
                return 1

            exe = path.with_suffix("")
            result = run([str(exe)])
            actual = result.returncode
            if actual != expected:
                print(f"FAIL: {name} returned {actual}, expected {expected}")
                return 1

        for name, source in INVALID.items():
            path = tmp / name
            path.write_text(source)
            result = run([sys.executable, str(COMPILER), str(path)])
            if result.returncode == 0:
                print(f"FAIL: compiler accepted invalid {name}")
                return 1
            if path.with_suffix("").exists() or path.with_suffix(".s").exists():
                print(f"FAIL: compiler left output behind for invalid {name}")
                return 1

    print("All stage 1 tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

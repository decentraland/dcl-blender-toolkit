#!/usr/bin/env python3
"""Check all Python files in src/ for syntax errors."""

import os
import py_compile
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def main():
    errors = []
    count = 0

    for dirpath, dirnames, filenames in os.walk(SRC_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, filename)
            count += 1
            try:
                py_compile.compile(filepath, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(str(e))

    print(f"Checked {count} Python files")

    if errors:
        print(f"\n{len(errors)} syntax error(s) found:")
        for err in errors:
            print(f"  {err}")
        sys.exit(1)

    print("All files OK")


if __name__ == "__main__":
    main()

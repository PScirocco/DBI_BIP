"""pytest 無しで bisim/tests/ の全テストを実行する。

    python -m bisim.selftest
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback

from bisim import tests as _tests_pkg


def main() -> int:
    total = fail = 0
    for mod_info in pkgutil.iter_modules(_tests_pkg.__path__):
        if not mod_info.name.startswith("test_"):
            continue
        mod = importlib.import_module(f"bisim.tests.{mod_info.name}")
        for name in sorted(vars(mod)):
            fn = getattr(mod, name)
            if not (name.startswith("test_") and callable(fn)):
                continue
            total += 1
            try:
                fn()
                print(f"PASS  {mod_info.name}.{name}")
            except Exception:  # noqa: BLE001
                fail += 1
                print(f"FAIL  {mod_info.name}.{name}")
                traceback.print_exc()
    print(f"\n{total - fail}/{total} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

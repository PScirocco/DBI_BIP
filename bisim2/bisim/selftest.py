"""pytest 無しで bisim/tests/ の全テストを実行する。

    python -m bisim.selftest             # 全テスト（モジュールごとに別プロセス）
    python -m bisim.selftest test_ui     # 指定モジュールだけ（同一プロセス）

引数なしのときは **テストモジュールごとにサブプロセスを分ける**。
UI/動画テストは 1 プロセスで多数回まわすと cv2/Qt がリソースを溜めて
ハングすることがあるため（テスト自体は健全）。
"""
from __future__ import annotations

import importlib
import pkgutil
import re
import subprocess
import sys
import traceback

from bisim import tests as _tests_pkg

_RESULT_RE = re.compile(r"(\d+)/(\d+) passed")


def _test_modules() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(_tests_pkg.__path__)
                  if m.name.startswith("test_"))


def _run_module(mod_name: str) -> int:
    """1 モジュールを同一プロセスで実行。"""
    mod = importlib.import_module(f"bisim.tests.{mod_name}")
    total = fail = 0
    for name in sorted(vars(mod)):
        fn = getattr(mod, name)
        if not (name.startswith("test_") and callable(fn)):
            continue
        total += 1
        try:
            fn()
            print(f"PASS  {mod_name}.{name}", flush=True)
        except Exception:  # noqa: BLE001
            fail += 1
            print(f"FAIL  {mod_name}.{name}", flush=True)
            traceback.print_exc()
    print(f"\n{total - fail}/{total} passed", flush=True)
    return 1 if fail else 0


def _run_all() -> int:
    grand_total = grand_fail = 0
    any_error = False
    for name in _test_modules():
        proc = subprocess.run(
            [sys.executable, "-m", "bisim.selftest", name],
            capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        m = _RESULT_RE.search(proc.stdout)
        if m:
            passed, total = int(m.group(1)), int(m.group(2))
            grand_total += total
            grand_fail += total - passed
        else:
            any_error = True
            print(f"!! {name}: 結果を取得できませんでした（rc={proc.returncode}）", flush=True)
        if proc.returncode not in (0, 1):
            any_error = True
    print(f"\n==== 合計 {grand_total - grand_fail}/{grand_total} passed ====", flush=True)
    return 1 if (grand_fail or any_error) else 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        return _run_module(argv[0])
    return _run_all()


if __name__ == "__main__":
    sys.exit(main())

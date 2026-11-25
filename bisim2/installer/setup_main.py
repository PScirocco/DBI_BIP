"""BI-sim セットアップ（インストーラ）。PyInstaller で1つの EXE（BI-sim_setup_YYMMDD.exe）にする。

中に BI-sim 一式（dist/BI-sim を zip にした BI-sim_payload.zip）を持ち、実行すると:
  1. インストール先を選ぶ（既定 %LOCALAPPDATA%\\Programs\\BI-sim。管理者権限は不要）
     ※ BI-sim はログ・設定（bisim_app.json）・既定の出力を EXE と同じフォルダに書くので、
       書き込みのできるユーザーのフォルダに入れる（Program Files には入れない）
  2. 前のバージョンがあれば、プログラム（BI-sim.exe・_internal）だけ入れ替える。
     ログ・設定・出力（_log_BISim・bisim_app.json・bisim_output）や、ユーザーが置いたデータは残す
  3. スタートメニュー（BI-sim・BI-sim のアンインストール）と、デスクトップ（任意）にショートカットを作る
  4. Windows の「アプリ」（インストールされているアプリ）からアンインストールできるように登録する（HKCU）
     アンインストールは、インストール先の uninstall.bat（プログラム・ショートカット・登録を消す。
     ログ・設定・出力を消すかは聞く）

テスト用（画面なし）: python setup_main.py --silent --payload <zip> --dir <インストール先>
                       [--no-desktop] [--startmenu-dir <dir>] [--desktop-dir <dir>] [--reg-name <名前>]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

APP = "BI-sim"
EXE = "BI-sim.exe"
PROGRAM_ITEMS = (EXE, "_internal")                      # 入れ替える（消す）のはこれだけ
USER_ITEMS = ("_log_BISim", "bisim_app.json", "bisim_output")   # アンインストールで消すか聞くもの


def resource(name: str) -> Path:
    """EXE に同梱したファイル（PyInstaller は _MEIPASS、そのまま実行したときはこのファイルの横）。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def default_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / APP


def payload_info(payload: Path) -> str:
    p = payload.with_name("payload_info.txt")
    return p.read_text(encoding="utf-8").strip() if p.is_file() else ""


def _ps(cmd: str) -> str:
    """PowerShell を1回実行して標準出力を返す（ショートカット作成・デスクトップの場所の取得）。"""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "PowerShell の実行に失敗しました")
    return r.stdout.strip()


def desktop_dir() -> Path:
    try:
        return Path(_ps("[Environment]::GetFolderPath('Desktop')"))
    except Exception:  # noqa: BLE001
        return Path.home() / "Desktop"


def startmenu_dir() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / \
        "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP


def make_shortcut(lnk: Path, target: Path, workdir: Path, icon: Path | None = None) -> None:
    lnk.parent.mkdir(parents=True, exist_ok=True)
    q = lambda s: str(s).replace("'", "''")             # noqa: E731
    cmd = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(lnk)}');"
           f"$s.TargetPath='{q(target)}';$s.WorkingDirectory='{q(workdir)}';")
    if icon is not None:
        cmd += f"$s.IconLocation='{q(icon)},0';"
    _ps(cmd + "$s.Save()")


def is_running(dest: Path) -> bool:
    """インストール先の BI-sim.exe が動いているか（動いていると上書きできない）。"""
    exe = dest / EXE
    if not exe.exists():
        return False
    try:
        os.rename(exe, exe)                             # 使用中なら Windows は名前を変えさせない
        return False
    except OSError:
        return True


def write_uninstaller(dest: Path, lnks: list, reg_name: str) -> Path:
    """インストール先に uninstall.bat を書く。UTF-8 で書き、先頭で chcp 65001（コンソールの文字コードに依らない）。
    find・tasklist は Windows のものを絶対パスで呼ぶ（PATH に同名のコマンドがあっても間違えない）。"""
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal",
        'cd /d "%~dp0.."',
        f'"%SystemRoot%\\System32\\tasklist.exe" /FI "IMAGENAME eq {EXE}" 2>nul | '
        f'"%SystemRoot%\\System32\\find.exe" /I "{EXE}" >nul',
        "if not errorlevel 1 (",
        f"  echo {APP} が起動しています。終了してから、もう一度アンインストールしてください。",
        "  pause",
        "  exit /b 1",
        ")",
        f"echo {APP} をアンインストールします: %~dp0",
        f'if exist "%~dp0{EXE}" del /f /q "%~dp0{EXE}"',
        'if exist "%~dp0_internal" rd /s /q "%~dp0_internal"',
    ]
    for lnk in lnks:
        lines.append(f'if exist "{lnk}" del /f /q "{lnk}"')
    sm = startmenu_dir()
    lines += [
        f'rd "{sm}" 2>nul',
        f'"%SystemRoot%\\System32\\reg.exe" delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{reg_name}" /f >nul 2>&1',
        "echo.",
        "echo ログ・設定・出力（" + "・".join(USER_ITEMS) + "）も消しますか？",
        'set "ANS="',
        'set /p ANS="Y=消す / それ以外=残す: "',
        'if /I not "%ANS%"=="Y" goto keep',
    ]
    for it in USER_ITEMS:
        lines.append(f'if exist "%~dp0{it}\\" (rd /s /q "%~dp0{it}") else if exist "%~dp0{it}" del /f /q "%~dp0{it}"')
    lines += [
        ":keep",
        "echo アンインストールが終わりました。",
        '"%SystemRoot%\\System32\\timeout.exe" /t 3 >nul',
        # 自分自身を消して、フォルダが空なら消す
        '(goto) 2>nul & del /f /q "%~f0" & rd "%~dp0" 2>nul',
    ]
    bat = dest / "uninstall.bat"
    bat.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return bat


def register_uninstall(reg_name: str, dest: Path, bat: Path, version: str) -> None:
    import winreg
    size_kb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{reg_name}") as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, version or "")
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, str(dest))
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, str(dest / EXE))
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{bat}"')
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, int(size_kb))


def install(payload: Path, dest: Path, desktop: bool, progress=None, startmenu: Path | None = None,
            desktop_path: Path | None = None, reg_name: str = APP) -> list:
    """インストールする。戻り値は注意（ショートカットを作れなかった等）の一覧。"""
    notes = []
    dest.mkdir(parents=True, exist_ok=True)
    if is_running(dest):
        raise RuntimeError(f"{APP} が起動しています。終了してから、もう一度インストールしてください。")
    for it in PROGRAM_ITEMS:                            # 前のバージョンのプログラムだけ消す（ユーザーのデータは残す）
        p = dest / it
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    with zipfile.ZipFile(payload) as z:
        members = z.infolist()
        for i, m in enumerate(members, 1):
            z.extract(m, dest)
            if progress and (i % 50 == 0 or i == len(members)):
                progress(i, len(members))
    exe = dest / EXE
    if not exe.is_file():
        raise RuntimeError(f"展開した中に {EXE} がありません（セットアップの作り方を確認してください）")
    sm = startmenu or startmenu_dir()
    lnks = [sm / f"{APP}.lnk", sm / f"{APP} のアンインストール.lnk"]
    bat = write_uninstaller(dest, [], reg_name)       # ショートカットの場所が決まってから書き直す
    try:
        make_shortcut(lnks[0], exe, dest, exe)
        make_shortcut(lnks[1], bat, dest)
        if desktop:
            dl = (desktop_path or desktop_dir()) / f"{APP}.lnk"
            make_shortcut(dl, exe, dest, exe)
            lnks.append(dl)
    except Exception as e:  # noqa: BLE001
        notes.append(f"ショートカットを作れませんでした（{e}）。{exe} を直接起動してください。")
    bat = write_uninstaller(dest, lnks, reg_name)
    try:
        register_uninstall(reg_name, dest, bat, payload_info(payload))
    except Exception as e:  # noqa: BLE001
        notes.append(f"「アプリ」への登録ができませんでした（{e}）。アンインストールは {bat} で行えます。")
    return notes


# --------------------------------------------------------------------------- #
#  画面（tkinter）
# --------------------------------------------------------------------------- #
def run_gui(payload: Path) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:                                                # 画面の拡大率に合わせてくっきり表示する
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    root.title(f"{APP} セットアップ")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.grid()
    info = payload_info(payload)
    ttk.Label(frm, text=f"{APP}（OLED 焼き付き劣化シミュレータ）をインストールします。",
              font=("Meiryo UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    if info:
        ttk.Label(frm, text=f"バージョン: {info}").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
    ttk.Label(frm, text="インストール先").grid(row=2, column=0, sticky="w")
    var_dir = tk.StringVar(value=str(default_dir()))
    ent = ttk.Entry(frm, textvariable=var_dir, width=60)
    ent.grid(row=3, column=0, columnspan=2, sticky="we")

    def browse():
        d = filedialog.askdirectory(initialdir=var_dir.get() or str(default_dir()))
        if d:
            var_dir.set(str(Path(d) / APP) if Path(d).name != APP else d)
    ttk.Button(frm, text="参照...", command=browse).grid(row=3, column=2, padx=(6, 0))
    ttk.Label(frm, text="ログ・設定・出力はこのフォルダに作られます（書き込みのできる場所を選んでください）。"
                        "前のバージョンがあれば、プログラムだけ入れ替えます（ログ・設定・出力は残ります）。",
              wraplength=520, foreground="#555").grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 8))
    var_desk = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text="デスクトップにショートカットを作る", variable=var_desk).grid(
        row=5, column=0, columnspan=3, sticky="w")
    bar = ttk.Progressbar(frm, length=520, mode="determinate")
    bar.grid(row=6, column=0, columnspan=3, pady=(12, 4))
    var_msg = tk.StringVar(value="")
    ttk.Label(frm, textvariable=var_msg).grid(row=7, column=0, columnspan=3, sticky="w")
    btns = ttk.Frame(frm)
    btns.grid(row=8, column=0, columnspan=3, sticky="e", pady=(12, 0))
    b_go = ttk.Button(btns, text="インストール")
    b_go.grid(row=0, column=0, padx=4)
    b_cancel = ttk.Button(btns, text="キャンセル", command=root.destroy)
    b_cancel.grid(row=0, column=1)

    def done(dest: Path, notes: list, err: str | None):
        if err:
            b_go.state(["!disabled"])
            b_cancel.state(["!disabled"])
            var_msg.set("インストールできませんでした。")
            messagebox.showerror(f"{APP} セットアップ", err)
            return
        var_msg.set("インストールが終わりました。")
        msg = f"インストールが終わりました。\n{dest}"
        if notes:
            msg += "\n\n" + "\n".join(notes)
        if messagebox.askyesno(f"{APP} セットアップ", msg + f"\n\n{APP} を起動しますか？"):
            subprocess.Popen([str(dest / EXE)], cwd=str(dest))
        root.destroy()

    def work(dest: Path, desk: bool):
        def prog(i, n):
            root.after(0, lambda: (bar.configure(maximum=n, value=i), var_msg.set(f"展開中… {i} / {n}")))
        try:
            notes = install(payload, dest, desk, prog)
            root.after(0, lambda: done(dest, notes, None))
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            root.after(0, lambda: done(dest, [], msg))

    def go():
        dest = Path(var_dir.get().strip())
        if not dest.is_absolute():
            messagebox.showerror(f"{APP} セットアップ", "インストール先を、ドライブから始まる場所で指定してください。")
            return
        if (dest / EXE).exists() and not messagebox.askyesno(
                f"{APP} セットアップ", f"{dest} には前のバージョンがあります。上書き（更新）しますか？\n"
                                     "（ログ・設定・出力は残ります）"):
            return
        b_go.state(["disabled"])
        b_cancel.state(["disabled"])
        var_msg.set("インストールしています…")
        threading.Thread(target=work, args=(dest, var_desk.get()), daemon=True).start()

    b_go.configure(command=go)
    root.mainloop()


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{APP} セットアップ")
    ap.add_argument("--payload", type=Path, help="BI-sim_payload.zip（既定は EXE に同梱したもの）")
    ap.add_argument("--silent", action="store_true", help="画面なしでインストール（テスト用）")
    ap.add_argument("--dir", type=Path, help="インストール先（--silent のとき）")
    ap.add_argument("--no-desktop", action="store_true")
    ap.add_argument("--startmenu-dir", type=Path)
    ap.add_argument("--desktop-dir", type=Path)
    ap.add_argument("--reg-name", default=APP)
    a = ap.parse_args()
    payload = a.payload or resource("BI-sim_payload.zip")
    if not payload.is_file():
        sys.exit(f"BI-sim の本体（{payload.name}）が見つかりません")
    if a.silent:
        notes = install(payload, (a.dir or default_dir()).resolve(), not a.no_desktop,
                        startmenu=a.startmenu_dir, desktop_path=a.desktop_dir, reg_name=a.reg_name)
        print("OK", *notes, sep="\n")
    else:
        run_gui(payload)


if __name__ == "__main__":
    main()

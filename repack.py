#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deepseek-session-repack —— 把 DSH 越来越肥的会话日志重新压一遍。

原理（一句话）：DSH 每写一条记录就单独压一个小块，几万块攒下来压缩率只剩 1.5 倍；
把「第一条 header 单独一块 + 其余全部一块」重压一遍，同样内容能到 8 倍左右。
DSH 只校验第一块是不是正好一行 header，所以这么压它是认的。

安全性：
  · 只改压缩分块方式，**内容一行不动**；压完逐行比对，不一致就放弃这一份
  · 替换前留带时间戳的备份
  · 只有文件超过阈值（默认 20MB）才动手；没超过就什么都不做
  · 默认「先停 DSH → 替换 → 再启动」；不想重启可以用 --no-restart 只生成新文件

用法：
  python repack.py --dry                    只报告哪些会话会被压
  python repack.py                          按阈值执行（会重启 DSH）
  python repack.py --threshold-mb 0         全部重压（测试用）
  python repack.py --no-restart             只生成 <file>.repacked，自己手动换

依赖：pip install zstandard
"""
from __future__ import annotations

import argparse
import json
import io
import os
import platform
import shutil
import subprocess
import sys
import time

try:
    import zstandard as zstd
except ImportError:
    print("缺依赖：pip install zstandard")
    raise SystemExit(1)

IS_WIN = platform.system() == "Windows"
DEFAULT_DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
DEFAULT_LOG = os.path.join(DEFAULT_DSH_HOME, "repack.log")


def log(msg: str, path: str = DEFAULT_LOG) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def find_session_files(dsh_home: str):
    root = os.path.join(dsh_home, "sessions")
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name == "session.v4.jsonl.zstd":
                out.append(os.path.join(dirpath, name))
    return out


def rows_of(path: str):
    rows = []
    with open(path, "rb") as fh:
        with zstd.ZstdDecompressor().stream_reader(fh) as reader:
            for line in io.TextIOWrapper(reader, encoding="utf-8", errors="ignore"):
                line = line.rstrip("\n")
                if line.strip():
                    rows.append(line)
    return rows


def repack_file(src: str, dst: str, level: int = 10) -> tuple[bool, str]:
    """块1=header 单行，块2=其余全部。返回 (成功, 说明)。"""
    try:
        rows = rows_of(src)
    except Exception as e:  # noqa: BLE001
        return False, f"读不出来：{e}"
    if len(rows) < 3:
        return False, "行数太少，跳过"
    # header 内容校验：防止把已经损坏的文件再压一遍（2026-10-29 交叉验证建议）
    try:
        head_row = json.loads(rows[0])
        if str(head_row.get("type")) != "session":
            return False, "第一行不是 session header"
    except Exception:
        return False, "第一行解析不了（文件可能已损坏）"
    try:
        c = zstd.ZstdCompressor(level=level)
        f1 = c.compress((rows[0] + "\n").encode("utf-8"))
        f2 = c.compress(("\n".join(rows[1:]) + "\n").encode("utf-8"))
        with open(dst, "wb") as fh:
            fh.write(f1)
            fh.write(f2)
        back = rows_of(dst)
        if back != rows:
            return False, f"逐行不一致（{len(rows)} vs {len(back)}）"
        head = zstd.ZstdDecompressor().decompress(f1).decode("utf-8")
        if len([x for x in head.split("\n") if x.strip()]) != 1:
            return False, "第一块不是单行 header"
        return True, f"{len(rows)} 行一致"
    except Exception as e:  # noqa: BLE001
        return False, f"压不出来：{e}"


def stop_dsh(exe_hint: str | None = None) -> bool:
    if IS_WIN:
        name = os.path.basename(exe_hint) if exe_hint else "DeepSeek Harness.exe"
        subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True)
        for _ in range(15):
            time.sleep(2)
            out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                                 capture_output=True, text=True).stdout
            if name not in out:
                return True
        return False
    # macOS / Linux：按进程名宽松匹配
    for pattern in ("dsh web", "dsh-web", "deepseek-harness"):
        subprocess.run(["pkill", "-f", pattern], capture_output=True)
    time.sleep(3)
    return True


def start_dsh(exe_hint: str | None = None) -> None:
    if IS_WIN and exe_hint and os.path.exists(exe_hint):
        subprocess.Popen([exe_hint], close_fds=True)
    else:
        subprocess.Popen(["dsh", "web"], close_fds=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="重压 DSH 会话日志")
    ap.add_argument("--dsh-home", default=DEFAULT_DSH_HOME, help="DSH 数据目录（默认 ~/.dsh）")
    ap.add_argument("--threshold-mb", type=float, default=20.0, help="超过多少 MB 才压（默认 20）")
    ap.add_argument("--level", type=int, default=10, help="zstd 压缩等级（默认 10）")
    ap.add_argument("--dry", action="store_true", help="只报告，不改任何文件")
    ap.add_argument("--no-restart", action="store_true", help="不重启 DSH，只生成 .repacked 文件")
    ap.add_argument("--exe", default="", help="DSH 可执行文件路径（Windows 重启用）")
    ap.add_argument("--restart", action="store_true", help="允许停/启 DSH（不加这个就等同于 --no-restart）")
    a = ap.parse_args()

    files = find_session_files(a.dsh_home)
    if not files:
        log(f"没找到会话日志（{a.dsh_home}/sessions）")
        return 0

    th = a.threshold_mb * 1024 * 1024
    todo = [f for f in files if os.path.getsize(f) > th]
    log(f"扫描 {len(files)} 个会话，超过 {a.threshold_mb}MB 的有 {len(todo)} 个")
    for f in todo:
        log(f"  待处理 {os.path.getsize(f)/1048576:6.1f}MB  {f}")

    if not todo or a.dry:
        log("dry-run 或无需处理，结束")
        return 0

    prepared = []
    for src in todo:
        dst = src + ".repacked"
        ok, note = repack_file(src, dst, a.level)
        if ok:
            prepared.append((src, dst, os.path.getsize(src), os.path.getsize(dst)))
            log(f"  已压好 {os.path.basename(os.path.dirname(src))}: {os.path.getsize(src)/1048576:.1f}MB → {os.path.getsize(dst)/1048576:.1f}MB（{note}）")
        else:
            log(f"  跳过 {src}: {note}")

    if not prepared:
        return 0

    if a.no_restart or not a.restart:
        log("没有 --restart：新文件已生成（*.repacked），DSH 停掉后手动替换即可")
        log("提醒：替换前请再复制一份原文件（换盘/网盘）——别只靠同目录的自动备份")
        return 0

    log("提醒：即将停 DSH 并替换文件，每份都会先留 *.repack-bak-<时间戳>")
    log("      数据重要的话，现在 Ctrl+C 退出，改用 --no-restart 手动处理")
    log("停 DSH …")
    if not stop_dsh(a.exe or None):
        log("DSH 没停下来，放弃替换（新文件留着）")
        return 2
    log("DSH 已退出，开始替换")
    done = 0
    for src, dst, old, new in prepared:
        try:
            bak = src + f".repack-bak-{int(time.time())}"
            shutil.copy2(src, bak)
            # 原子替换：同盘 rename，中断时要么旧文件要么新文件，绝不会留下写了一半的会话
            os.replace(dst, src)
            done += 1
            log(f"  已替换 {os.path.basename(os.path.dirname(src))}: {old/1048576:.1f}MB → {os.path.getsize(src)/1048576:.1f}MB")
        except Exception as e:  # noqa: BLE001
            log(f"  替换失败 {src}: {e}")
    log("启动 DSH …")
    start_dsh(a.exe or None)
    log(f"完成，替换 {done}/{len(prepared)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

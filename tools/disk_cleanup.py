# -*- coding: utf-8 -*-
"""
AI电脑管家 磁盘清理工具
清理 pip 缓存、__pycache__、临时文件等，释放磁盘空间。
运行: python tools/disk_cleanup.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_size_mb(path):
    """计算目录/文件大小 (MB)"""
    path = Path(path)
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    try:
        total = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    except Exception:
        return 0
    return total / (1024 * 1024)


def format_size(mb):
    if mb >= 1024:
        return f"{mb / 1024:.1f}G"
    return f"{mb:.1f}M"


def main():
    print("  🧹 AI电脑管家 磁盘清理")
    print(f"  项目路径: {PROJECT_ROOT}")
    print()

    freed_total = 0
    stats = {}

    # 1. pip cache
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'cache', 'dir'],
            capture_output=True, text=True, timeout=10
        )
        pip_cache = Path(result.stdout.strip())
        if pip_cache.exists():
            s = get_size_mb(pip_cache)
            stats['pip cache'] = (pip_cache, s, None)
    except Exception:
        pass

    # 2. __pycache__ dirs in project
    pycache = list(PROJECT_ROOT.rglob('__pycache__'))
    pycache_size = sum(get_size_mb(p) for p in pycache)
    if pycache_size > 0:
        stats['__pycache__'] = (PROJECT_ROOT, pycache_size, pycache)

    # 3. Windows临时文件
    temp_dirs = [Path(os.environ.get('TEMP', '')) / 'pip-*', Path(os.environ.get('TEMP', ''))]
    for td in temp_dirs:
        try:
            td = Path(str(td))
            if not td.exists():
                continue
            s = get_size_mb(td)
            if s > 10:  # Only show if > 10MB
                stats[f'Temp ({td.name})'] = (td, s, None)
        except Exception:
            pass

    # 首页
    print("  ---- 可清理项 ----")
    total = 0

    for name, (path, size, detail) in stats.items():
        print(f"  {'📦' if 'cache' in name.lower() else '📁'} {name}: {format_size(size)}")
        total += size

    print(f"\n  总计可清理: {format_size(total)}")
    print()

    if total < 1:
        print("  系统干净，无需清理。")
        return

    choice = input("  是否清理? [y/N]: ").strip().lower()
    if choice not in ('y', 'yes'):
        print("  取消。")
        return

    # 选择项
    names = list(stats.keys())
    if len(names) > 1:
        print("\n  选择要清理的项 (多个用空格分隔，回车清理全部):")
        for i, name in enumerate(names, 1):
            print(f"  {i}. {name} ({format_size(stats[name][1])})")
        sel = input("  > ").strip()
    else:
        sel = ''

    if sel:
        targets = set()
        for s in sel.split():
            try:
                targets.add(names[int(s) - 1])
            except (ValueError, IndexError):
                pass
    else:
        targets = set(names)

    # 执行
    for name in targets:
        path, size, detail = stats[name]
        print(f"\n  清理 {name}... ", end='', flush=True)

        try:
            if name == 'pip cache':
                subprocess.run([sys.executable, '-m', 'pip', 'cache', 'purge'],
                               capture_output=True, timeout=30)
                print(f"✓ 释放 {format_size(size)}")
                freed_total += size

            elif name == '__pycache__':
                count = 0
                for p in detail:
                    try:
                        shutil.rmtree(p)
                        count += 1
                    except Exception:
                        pass
                print(f"✓ 移除 {count} 个目录，释放 {format_size(size)}")
                freed_total += size

            else:
                s_before = get_size_mb(PROJECT_ROOT.parent)
                # 安全清理 Temp 目录下的过期文件
                if 'pip-' in str(path):
                    for p in Path(os.environ.get('TEMP', '')).glob('pip-*'):
                        try:
                            if p.is_dir():
                                shutil.rmtree(p)
                            else:
                                p.unlink()
                        except Exception:
                            pass
                print(f"✓ 释放 {format_size(size)}")
                freed_total += size

        except Exception as e:
            print(f"✗ 失败: {e}")

    # 成果
    print(f"\n  ✅ 清理完成，释放约 {format_size(freed_total)}")
    usage = shutil.disk_usage(PROJECT_ROOT)
    print(f"  磁盘剩余: {usage.free / (1024**3):.1f}G/{usage.total / (1024**3):.0f}G "
          f"({usage.free / usage.total * 100:.0f}%)")


if __name__ == '__main__':
    main()
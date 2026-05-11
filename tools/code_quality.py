# -*- coding: utf-8 -*-
"""代码质量扫描工具 - 分析重复导入、长函数、代码坏味道"""
import ast
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_python_files(root):
    """递归查找所有 .py 文件"""
    files = []
    for dp, dn, fns in os.walk(root):
        dp_path = Path(dp)
        # 跳过虚拟环境和缓存
        if any(p in dp_path.parts for p in ('__pycache__', 'venv', '.venv', '.git', 'env')):
            continue
        for fn in fns:
            if fn.endswith('.py'):
                files.append(dp_path / fn)
    return sorted(files)


def analyze_file(filepath):
    """分析单个文件"""
    with open(filepath, encoding='utf-8', errors='replace') as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {
            'file': str(filepath),
            'lines': 0,
            'functions': 0,
            'classes': 0,
            'error': str(e),
            'duplicate_imports': {},
            'long_functions': [],
        }

    lines = source.count('\n')

    # 统计函数
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    # 统计类
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    # 查找重复导入
    import_counter = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            key = f"from {node.module or '.'} import {', '.join(a.name for a in node.names)}"
            import_counter[key] += 1
        elif isinstance(node, ast.Import):
            key = f"import {', '.join(a.name for a in node.names)}"
            import_counter[key] += 1

    duplicates = {k: v for k, v in import_counter.items() if v > 1}

    # 查找长函数 (>100 行)
    long_funcs = []
    for fn in funcs:
        if hasattr(fn, 'lineno') and hasattr(fn, 'end_lineno'):
            length = fn.end_lineno - fn.lineno
            if length > 100:
                long_funcs.append((fn.name, fn.lineno, length))

    long_funcs.sort(key=lambda x: x[2], reverse=True)

    return {
        'file': str(filepath),
        'lines': lines,
        'functions': len(funcs),
        'classes': len(classes),
        'error': None,
        'duplicate_imports': duplicates,
        'long_functions': long_funcs,
    }


def main():
    print("\n\033[1m\033[96m  AI电脑管家 - 代码质量扫描\033[0m\n")

    files = find_python_files(PROJECT_ROOT)
    print(f"  扫描 {len(files)} 个 Python 文件...\n")

    total_issues = 0
    for filepath in files:
        relpath = filepath.relative_to(PROJECT_ROOT)
        result = analyze_file(filepath)

        if result['error']:
            print(f"\033[91m  ✗ {relpath}\033[0m - 语法错误: {result['error']}")
            total_issues += 1
            continue

        issues = []

        # 重复导入
        if result['duplicate_imports']:
            for imp, count in result['duplicate_imports'].items():
                issues.append(f"      重复导入 x{count}: {imp}")

        # 长函数
        if result['long_functions']:
            top = result['long_functions'][:3]
            for name, lineno, length in top:
                issues.append(f"      长函数: {name}() ({length}行, 行{lineno})")

        # 超大文件
        if result['lines'] > 1000:
            issues.append(f"      ⚠ 超大文件: {result['lines']} 行, {result['functions']} 个函数")

        if issues:
            print(f"  \033[93m⚠ {relpath}\033[0m ({result['lines']}行, {result['functions']}个函数)")
            for issue in issues:
                print(issue)
            total_issues += 1
        else:
            pass  # 不输出无问题文件

    if total_issues == 0:
        print("  \033[92m✓ 未发现代码质量问题\033[0m")
    else:
        print(f"\n  \033[93m共 {total_issues} 个文件存在问题\033[0m")
        print(f"  建议: 长函数应拆分，重复导入应集中到文件顶部")


if __name__ == "__main__":
    sys.exit(main())
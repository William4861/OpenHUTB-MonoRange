#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OpenHUTB / CARLA 环境自检脚本
=============================
用途：装完环境后跑一遍，一次看清"能不能开工"。

使用：
    python check_env.py

输出四块：
    ① Python 与依赖   ② 显卡与显存   ③ OpenHUTB 目录   ④ carla 包导入

作者：AI 代写（工具代码，非毕设核心算法）
"""
import os
import sys
import glob
import subprocess

SEP = "=" * 62


def sec(title):
    print("\n" + SEP)
    print("  " + title)
    print(SEP)


# ---------------------------------------------------------------- ① Python
def check_python():
    sec("① Python 与依赖")
    v = sys.version_info
    print(f"Python 解释器 : {sys.executable}")
    print(f"版本          : {v.major}.{v.minor}.{v.micro}")
    # OpenHUTB 的 whl 支持 3.7–3.14
    if (3, 7) <= (v.major, v.minor) <= (3, 14):
        print("版本判断      : ✅ 在 OpenHUTB 支持范围（3.7–3.14）")
    else:
        print("版本判断      : ❌ 超出 3.7–3.14，需要换 Python")

    print("\n关键第三方库：")
    for mod, hint in [
        ("numpy", "必备（矩阵运算）"),
        ("cv2", "可选（图像校验）"),
        ("PIL", "可选（图像校验）"),
    ]:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            print(f"  {mod:<8} ✅ {ver}   {hint}")
        except ImportError:
            flag = "必备" if mod == "numpy" else "可选"
            print(f"  {mod:<8} ❌ 未安装（{flag}）-> pip install {mod if mod!='PIL' else 'pillow'}")


# ---------------------------------------------------------------- ② GPU
def check_gpu():
    sec("② 显卡与显存")
    # nvidia-smi 是最可靠的方式
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.used,driver_version",
             "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode("utf-8", errors="ignore").strip()
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            print(f"显卡      : {parts[0]}")
            print(f"显存      : {parts[1]}（已用 {parts[2]}）")
            print(f"驱动      : {parts[3]}")
            # 解析显存 MB
            try:
                total_mb = int(parts[1].split()[0])
                if total_mb >= 6000:
                    print(f"判断      : ✅ {total_mb} MB ≥ 6GB，够跑 OpenHUTB")
                else:
                    print(f"判断      : ⚠️ 只有 {total_mb} MB，可能吃力")
            except Exception:
                pass
    except Exception:
        print("nvidia-smi 调用失败（可能没装 N 卡驱动，或不在 PATH）")
        print("→ 手动确认：任务管理器 → 性能 → GPU")


# ---------------------------------------------------------------- ③ 目录
def check_dirs():
    sec("③ OpenHUTB 目录")
    # 从脚本所在目录往上两级找 hutb
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "hutb"),
        os.path.join(here, "..", "..", "hutb"),
        r"D:\code_work\OpenHUTB\hutb",
    ]
    found = None
    for c in candidates:
        c = os.path.abspath(c)
        if os.path.isdir(c):
            found = c
            break
    if not found:
        print("❌ 没找到 hutb 目录")
        print("   预期位置：" + " / ".join(os.path.abspath(c) for c in candidates))
        return None
    print(f"✅ 找到 hutb: {found}")

    # 关键子路径
    checks = [
        ("模拟器主程序", os.path.join(found, "CarlaUE4.exe")),
        ("PythonAPI 目录", os.path.join(found, "PythonAPI")),
        ("whl 安装包目录", os.path.join(found, "PythonAPI", "carla", "dist")),
    ]
    for name, path in checks:
        print(f"  {'✅' if os.path.exists(path) else '❌'} {name}: {path}")

    # 列出 whl
    whl_dir = os.path.join(found, "PythonAPI", "carla", "dist")
    if os.path.isdir(whl_dir):
        whls = glob.glob(os.path.join(whl_dir, "*.whl"))
        print(f"\n  可安装的 whl（{len(whls)} 个）：")
        for w in whls:
            print("    " + os.path.basename(w))
    return found


# ---------------------------------------------------------------- ④ carla
def check_carla():
    sec("④ carla 包导入")
    try:
        import carla
        print("✅ import carla 成功")
        for attr in ("__version__", "VERSION"):
            if hasattr(carla, attr):
                print(f"  {attr} = {getattr(carla, attr)}")
                break
        # 关键类是否都在
        for cls in ("Client", "World", "BlueprintLibrary", "Transform", "Location"):
            print(f"  {'✅' if hasattr(carla, cls) else '❌'} carla.{cls}")
    except ImportError as e:
        print(f"❌ import carla 失败：{e}")
        print("\n   解决：")
        print("     1) cd <hutb>/PythonAPI/carla/dist")
        print("     2) pip install hutb-*.whl   （或 carla-*.whl）")
        print("     3) 确认 pip 用的就是当前这个 Python：python -m pip install ...")


def main():
    print("OpenHUTB 环境自检")
    check_python()
    check_gpu()
    check_dirs()
    check_carla()
    print("\n" + SEP)
    print("  自检结束。四项都 ✅ 就可以跑采集脚本了。")
    print(SEP)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OpenHUTB 连接诊断（最小验证）
============================
只做三件事：连上 → 读世界 → 报告状态。
不 spawn 任何东西，不会改模拟器状态。

用法（模拟器必须已启动）：
    cd /d D:\code_work\OpenHUTB\hutb
    D:\code_work\Python3.13.7\python.exe "D:\code_work\trae_project\PreparationForInterview\毕设\code\diag_connect.py"
"""
import sys
import time

try:
    import carla
except ImportError:
    print("❌ 没有 carla 模块。检查是不是用了 Python3.13.7")
    sys.exit(1)

print("=" * 60)
print("  ① 创建客户端")
print("=" * 60)
client = carla.Client('127.0.0.1', 2000)
client.set_timeout(30.0)          # 给足 30 秒
print("  ✅ client 创建成功（此时还没真正连上）")

print()
print("=" * 60)
print("  ② 请求 world（真正握手，卡住就是这里）")
print("=" * 60)
t0 = time.time()
try:
    world = client.get_world()
except RuntimeError as e:
    print(f"  ❌ 失败，耗时 {time.time()-t0:.1f}s")
    print(f"     错误：{e}")
    print()
    print("  → 说明模拟器没响应。请：")
    print("     1) 确认 CarlaUE4.exe 窗口还在、画面能动")
    print("     2) 关掉 CarlaUE4.exe 重新双击，等完全加载（能拖视角）")
    print("     3) 再跑本脚本")
    sys.exit(2)
print(f"  ✅ get_world 成功，耗时 {time.time()-t0:.1f}s")

print()
print("=" * 60)
print("  ③ 读取世界状态")
print("=" * 60)
try:
    m = world.get_map()
    print(f"  地图名    : {m.name}")
    print(f"  spawn 点  : {len(m.get_spawn_points())} 个")
    vehicles = world.get_actors().filter('vehicle.*')
    print(f"  当前车辆  : {len(vehicles)} 辆")
    sensors = world.get_actors().filter('sensor.*')
    print(f"  当前传感器: {len(sensors)} 个")
    st = world.get_settings()
    print(f"  同步模式  : {'✅ 开' if st.synchronous_mode else '❌ 关（异步）'}")
    print(f"  固定步长  : {st.fixed_delta_seconds}")
    print()
    print("=" * 60)
    print("  ✅ 一切正常，可以跑 collect_dataset.py")
    print("=" * 60)
except Exception as e:
    print(f"  ⚠️ 连上了但读状态出错：{e}")
    sys.exit(3)

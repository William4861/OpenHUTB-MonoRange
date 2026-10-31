#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OpenHUTB 车载单目数据集采集脚本（KITTI 格式）
==============================================
毕设：基于 OpenHUTB 仿真的车载单目视觉测距与目标定位方法研究

产物结构：
    dataset/
    ├── image_2/  000000.png ...      相机拍到的图
    ├── label_2/  000000.txt ...      每行一个目标（KITTI 格式）
    ├── calib/    000000.txt ...      内参 P2 矩阵
    └── meta.json                     相机参数、场景、帧数、时间

使用：
    1) 先启动模拟器（另开一个窗口）：
         cd <hutb目录>
         CarlaUE4.exe            （Windows）
    2) 等模拟器界面出来（能拖动视角），再跑本脚本：
         python collect_dataset.py --frames 1200
    3) 采集中途可以 Ctrl+C，已采的帧不会丢

参数：
    --frames N        采多少帧（默认 1200，对应毕设验收标准）
    --host / --port   模拟器地址（默认 127.0.0.1:2000）
    --out DIR         输出目录（默认 ./dataset）
    --width / --height  图像分辨率（默认 1280x720）
    --fov             水平视场角，度（默认 90）
    --vehicles N      生成多少辆车（默认 30）
    --map NAME        指定地图（默认用模拟器当前地图）
    --min-dist / --max-dist  只保留这个距离范围内的目标（默认 1–60 米）

作者：AI 代写（数据采集工具，非毕设核心算法）
      核心算法（测距/定位/改进方法）由王远本人实现
"""
import argparse
import json
import math
import os
import sys
import time
import random

try:
    import carla
except ImportError:
    print("❌ 没装 carla 包。先跑 check_env.py 看环境，再：")
    print("   cd <hutb>/PythonAPI/carla/dist && pip install hutb-*.whl")
    sys.exit(1)

import numpy as np

# KITTI 类别映射：CARLA 的 vehicle.* 统一归到这几类
# 想更细可以按 blueprint id 再分（vehicle.audi.* 等）
KITTI_TYPE = "Car"

# 相机坐标系说明（很重要，答辩会问）
# ---------------------------------------------------------------
# CARLA 世界坐标：x 向前(北)、y 向右(东)、z 向上
# CARLA 相机局部系（transform.inverse_transform() 变换后）：x 前、y 右、z 上
# KITTI 相机坐标系：x 右、y 下、z 前
# 所以转换关系：
#     X_kitti =  y_cam_local
#     Y_kitti = -z_cam_local
#     Z_kitti =  x_cam_local
# 投影：
#     u = fx * X / Z + cx
#     v = fy * Y / Z + cy
# ---------------------------------------------------------------


class Camera:
    """把 CARLA 相机参数换算成内参矩阵"""

    def __init__(self, width, height, fov_deg):
        self.width = width
        self.height = height
        self.fov = fov_deg
        # CARLA 的 fov 是【水平】视场角
        self.fx = (width / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
        self.fy = self.fx                      # 方形像素
        self.cx = width / 2.0
        self.cy = height / 2.0

    def intrinsic(self):
        """3x3 内参 K"""
        return np.array([
            [self.fx, 0.0,      self.cx],
            [0.0,     self.fy,  self.cy],
            [0.0,     0.0,      1.0],
        ])

    def projection(self):
        """3x4 投影矩阵 P（KITTI calib 里的 P2）"""
        return np.array([
            [self.fx, 0.0,     self.cx, 0.0],
            [0.0,     self.fy, self.cy, 0.0],
            [0.0,     0.0,     1.0,     0.0],
        ])

    def as_dict(self):
        return {"width": self.width, "height": self.height, "fov": self.fov,
                "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy}


def world_to_camera_kitti(world_loc, camera_transform):
    """
    世界坐标 → KITTI 相机坐标

    用官方 Transform.inverse_transform()（比手写矩阵求逆更可靠、更快）。
    它返回相机局部系坐标：x 前、y 右、z 上。
    再换轴成 KITTI 约定（x 右、y 下、z 前）：X=y, Y=-z, Z=x
    """
    p = camera_transform.inverse_transform(world_loc)
    return np.array([p.y, -p.z, p.x], dtype=np.float64)


def bbox3d_to_bbox2d(actor, cam, camera_transform):
    """
    CARLA 的 3D 包围盒 → 图像上的 2D 外包框

    做法：把 3D 盒的 8 个角点都投到图上，取外包矩形（比只投中心点准）

    返回 (x1, y1, x2, y2) 或 None（盒子完全在相机后面）
    """
    bb = actor.bounding_box
    # 🔴 官方 API：直接给出 8 个角点的【世界坐标】
    # （会自动处理 bb.location 偏移和 bb.rotation，比手算更准）
    corners_world = bb.get_world_vertices(actor.get_transform())

    us, vs = [], []
    for wp in corners_world:
        p = world_to_camera_kitti(wp, camera_transform)
        if p[2] <= 0.1:                # 在相机背后或太近，跳过这个角
            continue
        u = cam.fx * p[0] / p[2] + cam.cx
        v = cam.fy * p[1] / p[2] + cam.cy
        us.append(u)
        vs.append(v)

    if len(us) < 4:                    # 角点太少，说明基本在视野外
        return None
    return min(us), min(vs), max(us), max(vs)


def yaw_to_kitti_ry(actor_yaw_deg, camera_yaw_deg):
    """
    朝向角转换：世界 yaw → KITTI 相机系下的 ry（弧度，绕 Y 轴向下）

    简化处理（相机基本水平时足够准）：ry = -(yaw_obj - yaw_cam) 归一化到 [-pi, pi]
    严谨做法要用完整旋转矩阵投影，若相机有俯仰角需要修正
    """
    d = math.radians(actor_yaw_deg - camera_yaw_deg)
    ry = -d
    while ry > math.pi:
        ry -= 2 * math.pi
    while ry < -math.pi:
        ry += 2 * math.pi
    return ry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=2000)
    ap.add_argument("--frames", type=int, default=1200)
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fov", type=float, default=90.0)
    ap.add_argument("--vehicles", type=int, default=30)
    ap.add_argument("--map", default=None)
    ap.add_argument("--min-dist", type=float, default=1.0)
    ap.add_argument("--max-dist", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    random.seed(args.seed)
    cam = Camera(args.width, args.height, args.fov)
    print(f"内参：fx={cam.fx:.2f}  fy={cam.fy:.2f}  cx={cam.cx:.1f}  cy={cam.cy:.1f}")

    # ---------- 目录 ----------
    for sub in ("image_2", "label_2", "calib"):
        os.makedirs(os.path.join(args.out, sub), exist_ok=True)

    # ---------- 连接 ----------
    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)
    world = client.get_world()
    if args.map:
        print(f"切换地图 → {args.map}")
        world = client.load_world(args.map)
    print(f"地图：{world.get_map().name}")

    original_settings = world.get_settings()
    actors_to_destroy = []
    sensor = None

    try:
        # ================= 🔴 同步模式（最关键的一步）=================
        # 异步模式下传感器回调和 world 推进不同步 -> 图像和真值会【错帧】，标签全废
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = 0.05      # 20 Hz
        world.apply_settings(settings)

        tm = client.get_trafficmanager(8000)
        tm.set_synchronous_mode(True)

        # ---------- 生成车流 ----------
        bp_lib = world.get_blueprint_library()
        car_bps = bp_lib.filter("vehicle.*")
        spawn_points = world.get_map().get_spawn_points()
        random.shuffle(spawn_points)
        n_spawn = min(args.vehicles, len(spawn_points))

        ego = None
        for i, sp in enumerate(spawn_points[:n_spawn]):
            bp = random.choice(car_bps)
            if bp.has_attribute("role_name"):
                bp.set_attribute("role_name", "ego" if i == 0 else "npc")
            v = world.try_spawn_actor(bp, sp)
            if v is None:
                continue
            actors_to_destroy.append(v)
            v.set_autopilot(True, tm.get_port())
            if i == 0:
                ego = v

        if ego is None:
            print("❌ 一辆车都没生成，检查地图 spawn_points")
            return
        print(f"生成车辆：{len(actors_to_destroy)} 辆（ego = {ego.type_id}）")

        # ---------- 挂相机（第一人称，跟 ego 走）----------
        cam_bp = bp_lib.find("sensor.camera.rgb")
        cam_bp.set_attribute("image_size_x", str(args.width))
        cam_bp.set_attribute("image_size_y", str(args.height))
        cam_bp.set_attribute("fov", str(args.fov))
        cam_bp.set_attribute("sensor_tick", "0.0")     # 每个 tick 都出图

        # 装在车头稍微上方，模拟车载前视相机
        cam_tf = carla.Transform(carla.Location(x=1.5, y=0.0, z=1.6))
        sensor = world.spawn_actor(cam_bp, cam_tf, attach_to=ego)
        print(f"相机已挂载：{args.width}x{args.height}, fov={args.fov}")

        # ---------- 图像缓冲 ----------
        latest_image = {"frame": None, "image": None}

        def on_image(image):
            latest_image["frame"] = image.frame
            latest_image["image"] = image

        sensor.listen(on_image)

        # 先 tick 几次让场景稳定
        for _ in range(20):
            world.tick()

        # ---------- 主循环 ----------
        saved = 0
        attempted = 0
        t0 = time.time()
        print(f"\n开始采集：目标 {args.frames} 帧（只保留有目标的帧）")
        print("按 Ctrl+C 可中断\n")

        while saved < args.frames:
            world.tick()
            attempted += 1

            if latest_image["image"] is None:
                continue

            cam_transform = sensor.get_transform()
            vehicles = list(world.get_actors().filter("vehicle.*"))
            cam_loc = cam_transform.location

            lines = []
            for v in vehicles:
                if v.id == ego.id:
                    continue                      # 跳过自车

                # 距离过滤
                d = cam_loc.distance(v.get_transform().location)
                if d < args.min_dist or d > args.max_dist:
                    continue

                # 2D 投影框
                box2d = bbox3d_to_bbox2d(v, cam, cam_transform)
                if box2d is None:
                    continue
                x1, y1, x2, y2 = box2d
                # 只要和画面有交集就留
                if x2 < 0 or x1 > args.width or y2 < 0 or y1 > args.height:
                    continue
                x1 = max(0.0, min(x1, args.width - 1))
                x2 = max(0.0, min(x2, args.width - 1))
                y1 = max(0.0, min(y1, args.height - 1))
                y2 = max(0.0, min(y2, args.height - 1))
                if x2 - x1 < 4 or y2 - y1 < 4:      # 太小的目标没意义
                    continue

                # 3D 真值（KITTI 相机坐标系）
                v_tf = v.get_transform()
                center_kitti = world_to_camera_kitti(v_tf.location, cam_transform)
                if center_kitti[2] <= 0.1:
                    continue

                bb = v.bounding_box
                # extent 是半长 -> 尺寸要乘 2
                h = 2.0 * bb.extent.z
                w = 2.0 * bb.extent.y
                l = 2.0 * bb.extent.x
                ry = yaw_to_kitti_ry(v_tf.rotation.yaw, cam_transform.rotation.yaw)

                # KITTI 格式一行：
                # type truncated occluded alpha x1 y1 x2 y2 h w l x y z ry
                #   truncated/occluded 仿真里没有，填 0
                #   alpha 是观测角，用 ry - atan2(x, z) 近似
                alpha = ry - math.atan2(center_kitti[0], center_kitti[2])
                while alpha > math.pi:  alpha -= 2 * math.pi
                while alpha < -math.pi: alpha += 2 * math.pi

                lines.append(
                    f"{KITTI_TYPE} 0 0 {alpha:.4f} "
                    f"{x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f} "
                    f"{h:.4f} {w:.4f} {l:.4f} "
                    f"{center_kitti[0]:.4f} {center_kitti[1]:.4f} {center_kitti[2]:.4f} "
                    f"{ry:.4f}"
                )

            if not lines:
                continue                              # 空帧不要

            idx = saved
            name = f"{idx:06d}"
            latest_image["image"].save_to_disk(
                os.path.join(args.out, "image_2", name + ".png"))
            with open(os.path.join(args.out, "label_2", name + ".txt"), "w",
                      encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            with open(os.path.join(args.out, "calib", name + ".txt"), "w",
                      encoding="utf-8") as f:
                P = cam.projection()
                f.write("P2: " + " ".join(f"{x:.6f}" for x in P.flatten()) + "\n")

            saved += 1
            if saved % 50 == 0:
                el = time.time() - t0
                print(f"  {saved}/{args.frames} 帧  "
                      f"（尝试 {attempted} 次，有效 {saved}，"
                      f"{saved/max(el,1e-6):.1f} 帧/秒）")

        # ---------- 收尾 ----------
        meta = {
            "scene": world.get_map().name,
            "frames": saved,
            "attempted_ticks": attempted,
            "camera": cam.as_dict(),
            "kitti_type": KITTI_TYPE,
            "min_dist": args.min_dist,
            "max_dist": args.max_dist,
            "synchronous": True,
            "fixed_delta_seconds": 0.05,
            "note": "坐标已转换为 KITTI 相机系（x右 y下 z前）；extent 已乘 2 成为完整尺寸",
        }
        with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 完成：{saved} 帧 → {os.path.abspath(args.out)}")
        print(f"   内参已写入 meta.json 与 calib/*.txt")
        print(f"   用时 {time.time()-t0:.1f}s")

    except KeyboardInterrupt:
        print("\n⚠️ 已中断，已采的帧保留")
    finally:
        # ---------- 恢复现场（必须做，否则模拟器下次起不来）----------
        print("清理中……")
        if sensor is not None:
            try:
                sensor.stop()
                sensor.destroy()
            except Exception:
                pass
        for a in actors_to_destroy:
            try:
                a.destroy()
            except Exception:
                pass
        try:
            world.apply_settings(original_settings)
            tm.set_synchronous_mode(False)
        except Exception:
            pass
        print("已恢复异步模式，车辆已销毁")


if __name__ == "__main__":
    main()

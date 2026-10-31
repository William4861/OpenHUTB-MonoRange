#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据集可视化验收
================
把 KITTI label 里的 2D 框画回原图，并标上真实距离。
肉眼一看就知道：框画得准不准、距离对不对。

用法：
    cd /d D:\code_work\OpenHUTB\hutb
    D:\code_work\Python3.13.7\python.exe "D:\code_work\trae_project\PreparationForInterview\毕设\code\verify_dataset.py"

输出：dataset/_verify/  下若干张带框的图 + 一份统计
"""
import os
import sys
import glob

try:
    import cv2
except ImportError:
    print("❌ 没有 cv2。hutb 装了 opencv-contrib-python，检查是否用了 Python3.13.7")
    sys.exit(1)

ROOT = r"D:\code_work\OpenHUTB\hutb\dataset"
IMG_DIR = os.path.join(ROOT, "image_2")
LBL_DIR = os.path.join(ROOT, "label_2")
OUT_DIR = os.path.join(ROOT, "_verify")
os.makedirs(OUT_DIR, exist_ok=True)


def parse_line(line):
    """KITTI 一行 → dict"""
    p = line.split()
    if len(p) < 15:
        return None
    return {
        "type": p[0],
        "x1": float(p[4]), "y1": float(p[5]),
        "x2": float(p[6]), "y2": float(p[7]),
        "h": float(p[8]), "w": float(p[9]), "l": float(p[10]),
        "X": float(p[11]), "Y": float(p[12]), "Z": float(p[13]),
        "ry": float(p[14]),
    }


def main():
    labels = sorted(glob.glob(os.path.join(LBL_DIR, "*.txt")))
    if not labels:
        print(f"❌ {LBL_DIR} 里没有 label")
        sys.exit(1)

    print("=" * 62)
    print(f"  共 {len(labels)} 帧，逐帧统计")
    print("=" * 62)

    total_objs = 0
    z_all = []
    hpx_all = []
    drawn = 0

    for lp in labels:
        fid = os.path.splitext(os.path.basename(lp))[0]
        ip = os.path.join(IMG_DIR, fid + ".png")
        if not os.path.exists(ip):
            print(f"  ⚠️ {fid}: 没有对应图片")
            continue

        img = cv2.imread(ip)
        if img is None:
            print(f"  ⚠️ {fid}: 图片读不出来")
            continue

        objs = []
        with open(lp, encoding="utf-8") as f:
            for line in f:
                o = parse_line(line.strip())
                if o:
                    objs.append(o)
        total_objs += len(objs)

        for o in objs:
            x1, y1, x2, y2 = (int(round(o["x1"])), int(round(o["y1"])),
                             int(round(o["x2"])), int(round(o["y2"])))
            z = o["Z"]
            hpx = o["y2"] - o["y1"]
            z_all.append(z)
            hpx_all.append(hpx)

            # 距离分档配色（BGR）
            if z < 20:
                color = (0, 255, 0)       # 绿：20m 内
            elif z < 40:
                color = (0, 200, 255)     # 橙黄：20-40m
            else:
                color = (0, 0, 255)       # 红：40m 外

            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            tag = f"{z:.1f}m h{hpx:.0f}px"
            cv2.putText(img, tag, (x1, max(y1 - 6, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

        # 左上角信息
        cv2.putText(img, f"{fid}  objs={len(objs)}", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

        # 只输出前 8 帧，节省磁盘
        if drawn < 8:
            out = os.path.join(OUT_DIR, f"{fid}_boxes.jpg")
            cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            drawn += 1

        if objs:
            zs_f = [o["Z"] for o in objs]
            print(f"  {fid}: {len(objs):2d} 个目标   Z {min(zs_f):.1f}–{max(zs_f):.1f} m")
        else:
            print(f"  {fid}:  0 个目标")

    print("=" * 62)
    print(f"  总目标数：{total_objs}")
    if z_all:
        zs = sorted(z_all)
        print(f"  距离范围：{zs[0]:.1f} – {zs[-1]:.1f} m")
        print(f"  距离中位数：{zs[len(zs)//2]:.1f} m")
        n5_20 = sum(1 for z in z_all if 5 <= z <= 20)
        n20_40 = sum(1 for z in z_all if 20 < z <= 40)
        n40 = sum(1 for z in z_all if z > 40)
        print(f"  5–20m：{n5_20} 个 ｜ 20–40m：{n20_40} 个 ｜ >40m：{n40} 个")
        hp = sorted(hpx_all)
        print(f"  框高像素：{hp[0]:.1f} – {hp[-1]:.1f} px（中位数 {hp[len(hp)//2]:.1f}）")
    print("=" * 62)
    print(f"  ✅ 可视化已输出 {drawn} 张 → {OUT_DIR}")
    print("=" * 62)


if __name__ == "__main__":
    main()

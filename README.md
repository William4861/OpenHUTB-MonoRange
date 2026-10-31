# OpenHUTB-MonoRange

> 基于 OpenHUTB 仿真的**车载单目视觉测距与目标定位**方法研究（本科毕业设计）
>
> 湖南工商大学 · 机器人工程 2027 届 · 王远

**一句话**：用一张单目相机图像，估计画面中车辆**离我多远**（测距）和**在世界里的位置**（定位），并在仿真数据集上量化误差。

---

## 🎯 目标指标

| 指标 | 目标值 | 说明 |
|---|---|---|
| 目标检测 | mAP ≥ 0.85 | 先把车框出来 |
| **测距误差（5–20 m）** | **≤ 8 %** | 相对误差 `|估计 − 真值| / 真值` |
| **测距误差（20–40 m）** | **≤ 15 %** | 远处框小，误差放大 |
| **定位误差** | **≤ 0.5 m** | 目标世界坐标与真值的欧氏距离 |

---

## 🧱 技术路线

```
OpenHUTB 仿真（CARLA 内核 + 无人机扩展）
        │  同步模式逐帧采集
        ▼
   数据集（1200 帧 · KITTI 格式）
   ├── image_2/     车载相机 RGB 图（1280×720, FOV 90°）
   ├── label_2/     每帧的 3D/2D 真值标注（15 字段）
   └── calib/       内参 P2 矩阵
        │
        ▼
   目标检测（YOLO）→ 得到每辆车的 2D 框
        │
        ▼
   测距（baseline + 改进）
   ├── B1 框高法      D = fx · H / h_pixel        ← 基准模型
   ├── B2 地平面法    用框底边纵坐标反推
   └── 改进：多线索融合 + 时序滤波 + 类别细分先验
        │
        ▼
   定位（反投影 + 地面平面约束）→ 世界坐标 (X, Y)
        │
        ▼
   误差评估（对比 baseline 与改进方法，含消融实验）
```

> 🔴 **本项目的核心**：老师明确要求「**方法创新**」—— 不只是跑通流程，而是要有**基准模型 + 改进方法 + 对比实验**。

---

## 📁 目录结构

```
OpenHUTB-MonoRange/
├── README.md              本文件
├── DEVLOG.md              开发日志（按日期记进展、决策、踩坑）
├── BUGS.md                问题记录（编号 + 现象 + 根因 + 修复）
├── .gitignore
├── requirements.txt
├── code/                  全部可执行脚本
│   ├── check_env.py       环境自检（Python / 显卡 / hutb 目录 / import carla）
│   ├── diag_connect.py    连接诊断（模拟器连不上时先跑这个）
│   ├── collect_dataset.py 数据集采集（同步模式 → 采帧 → 导 KITTI 真值）
│   ├── verify_dataset.py  数据可视化验收（把 2D 框画回原图，肉眼验证）
│   └── ...                （T1 测距 baseline / T2 融合改进 / T3 定位 待补）
├── docs/
│   ├── dataset_format.md  数据集格式说明（KITTI 15 字段逐个解释）
│   └── setup.md           环境搭建步骤（OpenHUTB 安装 + Python 包）
└── samples/               少量样本图（带框可视化，用于展示，不含完整数据集）
```

---

## 🚀 快速开始

### 1. 安装 OpenHUTB

见 [`docs/setup.md`](docs/setup.md)。

要点：
- OpenHUTB **2.10.1**（约 20 GB）
- Python **3.13** 对应 `hutb-2.10.1-cp313-cp313-win_amd64.whl`
- **pip 包名是 `hutb`，但代码里是 `import carla`** ← 容易踩

### 2. 自检环境

```bash
python code/check_env.py
```

四项全 ✅ 才能继续（Python 版本 / 显卡 / hutb 目录 / `import carla`）。

### 3. 启动模拟器

双击 `CarlaUE4.exe`，**等画面完全加载**（能拖视角）再往下。

### 4. 采集数据

```bash
python code/collect_dataset.py --frames 20
```

首次建议先采 20 帧试跑，确认没问题再采 1200 帧。

### 5. 验证数据

```bash
python code/verify_dataset.py
```

会在 `dataset/_verify/` 下生成带框的图，**肉眼确认框准不准**。

---

## 📊 数据集说明

**完整数据集（1200 帧）因体积原因不纳入本仓库**（约 1–2 GB）。

仓库内提供：
- **采集脚本**（可一键重跑，参数可调）
- **少量样本**（`samples/`，带框可视化）

复现方式：

```bash
# 1. 启动 OpenHUTB
# 2. 采集
python code/collect_dataset.py --frames 1200 --vehicles 80 --max-dist 80
```

格式详见 [`docs/dataset_format.md`](docs/dataset_format.md)。

---

## 🔬 关键实现说明

### 为什么必须用同步模式

OpenHUTB（CARLA 内核）默认是**异步**：世界推进和传感器出图各跑各的。

**后果**：你拿到第 N 张图时，物体可能已经在第 N+1 帧的位置了 → **图像和标注错帧，标签全废**。

**做法**：

```python
settings = world.get_settings()
settings.synchronous_mode = True
settings.fixed_delta_seconds = 0.05      # 20 Hz
world.apply_settings(settings)
...
world.tick()      # 阻塞，等所有传感器数据到齐才返回
```

### 内参是怎么来的

```python
fx = (width / 2) / tan(FOV / 2)      # 1280, FOV=90° → fx = 640
cx = width / 2                        # 640
cy = height / 2                       # 360
```

**`fx = 640` 的物理意义**：距离相机 **1 米**处、**1 米高**的物体，在图像上占 **640 个像素**。

### 3D 框怎么变成 2D 框

```python
corners_world = bb.get_world_vertices(actor.get_transform())   # 8 个角点的世界坐标
# 每个角点投影到图像 → 得到 8 个 (u, v)
# 取最小外接矩形 → 2D 框
```

**为什么不只投中心点**：盒子有体积，投影后不是中心对称的，只投中心会框小。

### 坐标系转换

```
CARLA 世界：x 前、y 右、z 上
KITTI 相机：x 右、y 下、z 前
      ↓
X_kitti =  y_cam ｜ Y_kitti = -z_cam ｜ Z_kitti = x_cam
```

---

## ⚠️ 已知限制

| # | 限制 | 影响 |
|---|---|---|
| 1 | 仅在**仿真数据**上验证，未在真实相片上测试 | 真实场景有镜头畸变、曝光变化，未覆盖 |
| 2 | 目标类别简化（所有 `vehicle.*` 统一标为 `Car`） | 未区分轿车/SUV/货车，高度先验误差偏大 |
| 3 | 单目固有的**尺度不确定性** | 这是方法本身的限制，论文中会讨论 |
| 4 | 采集脚本依赖 OpenHUTB 特定版本（2.10.1） | 换版本可能 API 不兼容 |

---

## 📄 论文与进展

- 开发日志：见 [`DEVLOG.md`](DEVLOG.md)（按日期记录每日进展与决策）
- 问题记录：见 [`BUGS.md`](BUGS.md)（遇到的问题及根因分析）

---

## 📜 依赖

见 [`requirements.txt`](requirements.txt)。

主要依赖由 OpenHUTB 的 whl 自动带入：`numpy`、`opencv-contrib-python`、`msgpack-rpc-python`。

---

## 🙏 致谢

| 项目 | 用途 | 协议 |
|---|---|---|
| [**OpenHUTB**](https://github.com/OpenHUTB/hutb) | 仿真环境（CARLA 内核 + 无人机/水下载具扩展） | MIT |
| [CARLA](https://carla.org/) | 自动驾驶仿真器内核 | MIT |
| [KITTI](http://www.cvlibs.net/datasets/kitti/) | 数据集标注格式参照 | CC BY-NC-SA 3.0 |
| [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) | 目标检测（后续使用） | AGPL-3.0 |

> 本项目代码采用 MIT 协议。仿真场景资产的版权归 OpenHUTB 及各原始资产作者所有。

---

## 📄 License

[MIT](LICENSE) © 2026 Yuan Wang


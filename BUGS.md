# BUGS · 问题记录

> 编号规则：`BUG-0001` 起，只增不改号。
> 每条记：**现象 → 根因 → 修复 → 教训**。
> 已修复的标 ✅，未修复/待观察的标 🟡。

---

## 环境与工具类

### ✅ BUG-0001 · `BoundingBox` 没有 `get_transform()` 方法

**现象**
```
AttributeError: 'BoundingBox' object has no attribute 'get_transform'
```
在把 3D 包围盒的 8 个角点算出来时崩。

**根因**
按 UE 的 `FBox` 习惯写了 `bb.get_transform(actor_tf)`，但 **CARLA 的 Python API 不提供这个方法**。
`carla.BoundingBox` 只有 `location` / `extent` / `rotation` 三个字段和 `get_world_vertices()`。

**修复**
```python
# ❌ 原
bb_tf = bb.get_transform(actor.get_transform())
corners = [bb_tf.transform(carla.Location(x=sx*ex, ...)) for ...]

# ✅ 现
corners_world = bb.get_world_vertices(actor.get_transform())   # 直接给 8 个世界坐标
```

**教训**
**写 CARLA Python API 前必须先 `dir()` 查实际方法**，不要凭 UE 的 C++ 接口印象。

---

### ✅ BUG-0002 · `Transform` 没有 `get_inverse()` 方法

**现象**
```
AttributeError: 'Transform' object has no attribute 'get_inverse'
```
在把世界坐标转到相机局部坐标时崩。

**根因**
同样按 C++ 习惯写的。CARLA Python 的 `Transform` 提供的是：
- `get_matrix()` —— 4×4 位姿矩阵
- **`get_inverse_matrix()`** —— 逆矩阵
- **`inverse_transform(location)`** —— 直接变换一个点

**修复**
```python
# ❌ 原
inv = camera_transform.get_inverse()
p = inv.transform(world_loc)

# ✅ 现（一行搞定，C++ 内部实现）
p = camera_transform.inverse_transform(world_loc)
```

**教训**
同 BUG-0001。另外：**能用官方方法就别自己造**（我一开始还想用 numpy 求逆矩阵，多余且慢）。

---

### ✅ BUG-0003 · `carla` 模块没有 `__version__`

**现象**
```python
import carla
print(carla.__version__)
# AttributeError: module 'carla' has no attribute '__version__'
```

**根因**
OpenHUTB 打包 whl 时没往模块里写 `__version__` 属性。**`import` 本身是成功的。**

**修复**
```python
# ✅ 检查类是否存在，而不是查版本号
print('Client:', hasattr(carla, 'Client'), '| World:', hasattr(carla, 'World'))
```

**教训**
**验证"包能不能用"要看关键类在不在，不要依赖版本号属性。**

---

### ✅ BUG-0004 · 下载器中断 4 次，每次都要从头来

**现象**
`hutb_downloader.exe` 下到 5.7 GB / 13 GB / 16 GB 时中断，重跑后**从 0 开始**，已下部分全废。

**根因**
这个下载器的流程是 `git clone` + `git lfs pull`，**不是分块下载**：
- 每次启动都会 `git clone` 整个仓库 → **先删掉旧目录再重建**
- git-lfs 的 `incomplete/` 里的半成品文件**不支持续传**，未完成的对象要整个重下

**修复 / 规避**
- 🔴 **必须一口气下完**，中途不能关窗口、不能断网、不能睡眠
- 判断进度不要看 `X% (n/m)`（那是**文件个数**），要看 `.git/lfs` 目录的实际大小
- 总大小可以从仓库里的 LFS 指针读出来：
  ```python
  # 每个 .dat 文件的指针里有 size 字段
  git show <commit>:hutb_00000.dat   # → size 5368709120（5 GB）
  ```

**教训**
**大文件下载前先确认支不支持断点续传。** 不支持的话，先保证网络和电源稳定再开始。

---

### ✅ BUG-0005 · 中文 `.bat` 双击一闪就退出

**现象**
写了个中文内容的 `下载.bat`，双击后黑窗口闪一下就没了，什么都没执行。

**根因**
- 我用 **UTF-8 编码 + LF 换行**写的
- **cmd 只认 ASCII/GBK 编码 + CRLF 换行**
- 中文内容在 GBK 下被解释成乱码 → 第一行 `@echo off` 之后的命令全部语法错误 → 立即退出

**修复**
- 文件内容**全英文（纯 ASCII）**
- 换行必须是 **CRLF**
- 写文件后用 Python 校验：
  ```python
  raw = open('x.bat','rb').read()
  assert sum(1 for b in raw if b > 127) == 0   # 非 ASCII 字节必须为 0
  assert b'\r\n' in raw                         # 必须有 CRLF
  ```

**教训**
**给 Windows cmd 写批处理：纯 ASCII + CRLF，一个中文都不能有。**

---

### ✅ BUG-0006 · `config.py --map` 切换地图超时

**现象**
```
load map 'HutbCarlaCity'.
time-out of 10000ms while waiting for the simulator
```
地图没切成功，模拟器还在默认地图。

**根因**（两条，未完全确认）
1. `config.py` 里客户端超时只有 **10 秒**，大地图加载不够
2. 模拟器启动后默认在 **AirSim 模式**（有无人机），可能阻塞了 CARLA 的 RPC 请求

**修复 / 规避**
- **改用脚本自己 `load_world`**（`collect_dataset.py --map <名字>`），客户端超时 20 秒
- 或者干脆**不切地图**，用默认的 `Town10HD`（155 个 spawn 点，够用）

**教训**
**能用脚本做的事就别在窗口里点** —— 脚本可控、可重跑、能看到报错。

---

## 数据类

### 🟡 BUG-0007 · 每帧只有 2 个目标（生成了 30 辆车）

**现象**
20 帧采完，共 40 个目标，**每帧平均 2 个**。

**根因**
- Town10HD 是城区，155 个 spawn 点里用了 30 个，车辆**分散在全城**
- ego 车前方 60 米内、且在相机视野内的，只有 2 辆

**修复（待做）**
| 参数 | 现在 | 改成 |
|---|---|---|
| `--vehicles` | 30 | **80–100** |
| `--max-dist` | 60 | **80** |
| 新增 `--reset-interval` | — | 每 100 帧重置 ego 到新 spawn 点 |

**教训**
**「生成 30 辆车」不等于「画面里有 30 辆车」** —— 要看视野内和距离过滤后的实际数量。

---

### 🟡 BUG-0008 · 5–20 m 的样本严重不足

**现象**
距离分布：`18.4 – 35.8 m`，其中 **5–20 m 只有 6 个样本**（占比 15%）。

**根因**
- ego 车自己也在 autopilot 行驶，前方的车**保持相对稳定的距离**（跟车）
- 近距离（<20 m）的目标只在**路口/起步/拥挤路段**才出现
- 采的 20 帧是连续 1 秒，场景几乎没变

**影响**
🔴 **验收标准要求「5–20 m 误差 ≤8%」，但样本只有 6 个 → 无法支撑这个结论。**

**修复（待做）**
1. 增加车辆密度（BUG-0007 的方案）
2. **周期性重置 ego 位置**（每 100 帧换一个 spawn 点）→ 人为制造不同距离关系
3. 让 ego **降低速度**或**在路口停车**，等车流经过

**教训**
**采集前先想清"要什么分布"，否则采一堆数据还是不够用。**

---

### 🟡 BUG-0009 · 画面左侧近处的车没被标框

**现象**
`verify_dataset.py` 生成的图里，画面左侧一辆很近的黑车**没有标注框**，但它在画面里。

**根因**
代码里有一层过滤：
```python
if center_kitti[2] <= 0.1:
    continue          # 3D 中心在相机后方 → 整辆剔除
```
那辆车**3D 中心在相机侧后方**（因为相机装在车头，近处侧边的车中心确实在后面），所以被剔除了。

**这是设计选择，不是 bug**：中心在相机后方的目标，距离估出来无意义。

**但可以改进**
- 用 **2D 框中心是否在画面内** 来判断，而不是 3D 中心
- 或者放宽到 `center_kitti[2] > -5`（允许略微后方），并标记为"部分可见"

**教训**
**过滤条件要区分"看不见"和"看得见但中心在后面"** —— 后者在真实数据集里叫 truncated（截断）目标。

---

## 汇总

| 编号 | 类型 | 状态 |
|---|---|---|
| BUG-0001 | CARLA API | ✅ |
| BUG-0002 | CARLA API | ✅ |
| BUG-0003 | CARLA API | ✅ |
| BUG-0004 | 下载工具 | ✅ 规避 |
| BUG-0005 | 批处理编码 | ✅ |
| BUG-0006 | 地图切换 | ✅ 规避 |
| BUG-0007 | 数据质量 | 🟡 待改进 |
| BUG-0008 | 数据质量 | 🟡 待改进 |
| BUG-0009 | 过滤逻辑 | 🟡 待改进 |

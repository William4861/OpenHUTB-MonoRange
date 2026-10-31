# 环境搭建

> 从零到"能采数据"的完整步骤。踩过的坑都标出来了。

---

## 一、硬件要求（实测）

| 项 | OpenHUTB 官方要求 | 实测配置 | 判断 |
|---|---|---|---|
| 显卡 | NVIDIA **RTX 2070** 以上 | RTX 4060 Laptop **8 GB** | ✅ 够 |
| 内存 | **+16 GB** | 16 GB | 🟡 **刚好卡线**，跑时关掉浏览器等 |
| 磁盘 | 未标 | 需预留 **25 GB**（压缩包 20 GB + 解压后） | ✅ |
| 系统 | Windows 10+ | Win 10.0.26100 | ✅ |

---

## 二、下载 OpenHUTB（约 20 GB）

### 2.1 官方方式

```bash
# Windows
curl -fsSL -o dl.bat https://openhutb.github.io/dl.bat && dl.bat
```

`dl.bat` 是个壳，它实际会：
1. 下载 `hutb_downloader.exe`（9.3 MB）
2. **下载 `git_min.zip`（14 MB）并解压** ← 缺这个会报 `fatal: not in a git directory`
3. 用自带的 git + git-lfs 从 `git.code.tencent.com/OpenHUTB/release.git` 拉 LFS 大文件

### 2.2 🔴 必读的几个坑

**坑 1：`git_min.zip` 用 PowerShell 解压会静默失败**

```powershell
# ❌ 显示"展开完成"，但实际解压出 0 个文件（zip 里明明有 47 个条目、5 个 exe）
Expand-Archive -Path "git_min.zip" -DestinationPath "." -Force
```

**改用 Python**：
```python
import zipfile
zipfile.ZipFile('git_min.zip').extractall('.')     # ✅ 34 个文件正常出来
```

**坑 2：下载器不支持断点续传**

- 每次启动都会 `git clone` 整个仓库 → **先删旧目录再重建**
- 中断后重跑 = 从 0 开始，已下部分全废
- 🔴 **必须一口气下完**

**坑 3：进度百分比会误导**

日志里的 `Downloading LFS objects: 20% (1/5), 8.5 GB` 中：
- **`20%` 是按文件个数算的**（5 个对象完成 1 个）
- **后面的 `GB` 是十进制（10^9）**，不是 `du -h` 的 GiB（2^30）

**真实进度**要看磁盘：
```bash
du -sb D:/code_work/OpenHUTB/hutb/.git/lfs   # 二进制字节数
```

**总大小**可以从 LFS 指针读出来：
```bash
git -C hutb ls-tree -r <commit>                              # 找 .dat 文件
git -C hutb show <commit>:hutb_00000.dat                     # 看指针内容
# → version / oid sha256:xxx / size 5368709120  ← 5 GB
```

> 💡 如果 `git` 报 `not a git repository`，是因为 clone 未完成、缺 `HEAD`。
> 可以手动补：`echo "ref: refs/remotes/origin/master" > hutb/.git/HEAD`

**坑 4：下载完成后会自动清理**

下载器跑完会自动：
1. 合并 5 个 `.dat` → `hutb.zip`（20 GB）
2. **解压 `hutb.zip`**（69,724 个文件）
3. 删除 `.git`、`git_min.zip`、`git/` 目录

🔴 **所以本地不会留下 git 仓库** —— 也意味着**不需要 fork 上游仓库**。

---

## 三、安装 Python 包

### 3.1 Python 版本

OpenHUTB 2.10.1 提供 **cp37 / cp38 / cp39 / cp310 / cp311 / cp312 / cp313 / cp314** 共 8 个 whl。

**本项目用 Python 3.13.7** → 装 `cp313` 那个。

### 3.2 安装

```cmd
D:\code_work\Python3.13.7\python.exe -m pip install "D:\code_work\OpenHUTB\hutb\PythonAPI\carla\dist\hutb-2.10.1-cp313-cp313-win_amd64.whl"
```

**会连带装**：`msgpack-rpc-python`、`opencv-contrib-python`（53.8 MB）

### 3.3 🔴 最容易混的一点

| 项 | 名字 |
|---|---|
| **pip 包名** | **`hutb`**（装的时候用这个） |
| **代码里导入** | **`import carla`**（不是 `import hutb`） |

**装的是 hutb，导入的是 carla。** 别写错了。

### 3.4 验证

```cmd
D:\code_work\Python3.13.7\python.exe code\check_env.py
```

四项全 ✅ 才行：Python 版本 / 显卡显存 / hutb 目录 / `import carla`。

> ⚠️ **不要用 `carla.__version__` 验证** —— 这个属性不存在（BUG-0003）。
> 用 `hasattr(carla, 'Client')` 检查关键类。

---

## 四、启动模拟器

```
双击 D:\code_work\OpenHUTB\hutb\CarlaUE4.exe
```

**首次启动等 30 秒 – 2 分钟**（要加载场景资产）。

**成功的标志**：出现 3D 城市画面，**鼠标能拖动视角**。

### 🔴 关于"无人机模式"

启动后画面里可能有个**四旋翼无人机** + 右下角红色录制按钮 —— 这是 OpenHUTB 集成 AirSim 后的默认表现。

**这不影响采集**。因为：

```
CarlaUE4.exe  = 只是个【渲染器 + 物理引擎】
车 / 相机     = 全部由【Python 脚本 spawn】
```

所以**不需要在窗口里"切车辆模式"**，直接跑采集脚本就行。

### 切换地图（可选，容易失败）

```cmd
cd /d D:\code_work\OpenHUTB\hutb
D:\code_work\Python3.13.7\python.exe PythonAPI\util\config.py --list          # 看有哪些地图
D:\code_work\Python3.13.7\python.exe PythonAPI\util\config.py --map Town05_Opt
```

⚠️ **`--map` 切换经常会 `time-out of 10000ms`**（见 BUG-0006）→ 建议**用脚本的 `--map` 参数**，别用 config.py。

---

## 五、连不上模拟器怎么排查

**先跑诊断脚本**（只连不建，不会搞乱状态）：

```cmd
cd /d D:\code_work\OpenHUTB\hutb
D:\code_work\Python3.13.7\python.exe code\diag_connect.py
```

它会打印：
- 连接耗时（正常 < 1 秒）
- 当前地图名
- spawn 点数量
- 当前车辆/传感器数量
- 同步模式状态

**如果超时（30 秒）**：
1. 关掉 `CarlaUE4.exe`
2. 重新双击启动，**等画面完全加载**
3. 再跑诊断脚本

**常见原因**：模拟器还在加载地图（此时 RPC 不响应），不是真的坏了。

---

## 六、采集与验证

```cmd
# 采集（先采 20 帧试跑）
cd /d D:\code_work\OpenHUTB\hutb
D:\code_work\Python3.13.7\python.exe "D:\code_work\OpenHUTB-MonoRange\code\collect_dataset.py" --frames 20

# 验证（把 2D 框画回原图）
D:\code_work\Python3.13.7\python.exe "D:\code_work\OpenHUTB-MonoRange\code\verify_dataset.py"
```

**验证输出**：`dataset/_verify/*.jpg`，打开看框有没有紧贴车身。

---

## 七、清理磁盘

模拟器跑起来确认没问题后，可以删掉：

```
D:\code_work\OpenHUTB\hutb\hutb.zip     20 GB    ← 已解压，冗余
D:\code_work\OpenHUTB\git_min.zip       14 MB
```

**但先确认采过一次数据** —— 万一要重新解压还得用它。

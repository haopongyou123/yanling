# 衍灵部署指南

> 写给普通用户的安装手册 — 不懂编程也能看懂

---

## 衍灵是什么？

衍灵是一个能**自主运行、自我进化**的 AI 系统。你可以把它理解为一位"数字员工"——它有自己的感知、判断、行动和记忆能力，能在你睡觉的时候帮你处理事情。

衍灵可以安装在多种设备上，不同设备承担不同的职责，但它们可以协同工作。

---

## 设备与角色

衍灵集群由以下角色组成，你可以根据自己手头的设备选择安装：

| 角色 | 适合的设备 | 主要职责 |
|------|-----------|---------|
| **灯塔** (Lighthouse) | Mac Mini、高性能电脑 | 中央调度、深度思考、指挥全局 |
| **管家** (Butler) | Windows 电脑、笔记本 | 执行规则、本地任务处理 |
| **园丁** (Gardener) | Linux 服务器、WSL2 | 内容采集、自动生成、定时发布 |
| **掌簿** (Accountant) | NAS、树莓派、低功耗设备 | 密码管理、凭证存储、审计日志 |

> **最少只需一台设备**：如果你只有一台电脑，安装"灯塔"角色即可，衍灵会正常运行。
> 多台设备时，衍灵通过网络（ZeroTier 虚拟局域网）互相发现和通信。

---

## 一、安装前的准备

### 硬件要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 双核 2.0GHz | 四核及以上 |
| 内存 | 2GB | 4GB+（使用本地 AI 模型建议 8GB+）|
| 硬盘 | 1GB 可用空间 | 10GB（用于记忆存储和模型缓存）|
| 网络 | 宽带上网 | 稳定的互联网连接 |

### 软件要求

- **操作系统**：macOS 12+ / Windows 10+ / Ubuntu 22.04+
- **Python 版本**：3.10 ~ 3.12（安装时需联网下载）
- **Ollama**（可选）：如需使用本地小模型，需安装 Ollama

### 网络要求

- 如需多设备协同，需要安装 **ZeroTier**（虚拟组网软件）
- 如仅单机运行，不需要特殊网络配置

---

## 二、安装步骤

### 在所有设备上都执行的第一步

#### 1. 安装 Python 3

> 如果已安装 Python，可在终端运行 `python3 --version` 检查版本。

<details>
<summary><b>macOS 安装 Python</b></summary>

```bash
# 安装 Homebrew（包管理器，已安装可跳过）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python
brew install python@3.11
```
</details>

<details>
<summary><b>Windows 安装 Python</b></summary>

1. 打开浏览器，访问 https://www.python.org/downloads/
2. 下载 Python 3.11 或 3.12
3. 运行安装程序，**务必勾选"Add Python to PATH"**
4. 安装完成后，打开"命令提示符"，运行 `python --version` 确认
</details>

<details>
<summary><b>Linux / WSL2 安装 Python</b></summary>

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
python3 --version
```
</details>

#### 2. 获取衍灵代码

```bash
# 创建一个文件夹存放衍灵
mkdir -p ~/yanling
cd ~/yanling

# 从 GitHub 下载代码（如果没有 git，可手动下载 ZIP 解压）
git clone https://github.com/haopong123/yanling.git .
```

> **无 git 情况**：在浏览器打开 https://github.com/haopong123/yanling ，点击绿色"Code"按钮 → "Download ZIP" → 解压到 `~/yanling` 文件夹。

#### 3. 创建运行环境

```bash
# 在衍灵文件夹内执行
python3 -m venv .venv
source .venv/bin/activate      # Mac / Linux
# 或 .venv\Scripts\activate    # Windows

# 安装衍灵
pip install -e ".[web]"
```

> 这个过程需要联网下载依赖包，大约 1-5 分钟。如有失败，检查网络后重试。

---

### 按角色安装

#### 灯塔（Mac Mini / 高性能电脑）

灯塔是衍灵的大脑，担任中央调度。它使用云端 AI 模型（DeepSeek），每秒都在思考和学习。

```bash
# 设置角色（将下面这行加入 ~/.zshrc 或 ~/.bashrc）
export YANLING_NODE_ROLE=lighthouse

# 设置 API 密钥（必填，向管理员索取）
export DEEPSEEK_API_KEY="sk-你的密钥"

# 启动灯塔
cd ~/yanling
source .venv/bin/activate
python -m yanling.scenarios.embedded.run_persistent
```

启动后打开浏览器访问：**http://localhost:8764**

---

#### 管家（Windows 电脑）

管家是执行者，在日常使用的电脑上运行。它主要用于处理本地任务，如文件整理、定时提醒等。

```bash
# 设置角色
set YANLING_NODE_ROLE=butler

# 启动管家
cd %USERPROFILE%\yanling
.venv\Scripts\activate
python -m yanling.scenarios.embedded.run_persistent
```

启动后打开浏览器访问：**http://localhost:8764**

---

#### 园丁（Linux / WSL2 / 服务器）

园丁负责自动采集内容、生成文章、发布到各平台。它通常 7×24 小时运行。

```bash
# 设置角色
export YANLING_NODE_ROLE=gardener

# 启动园丁
cd ~/yanling
source .venv/bin/activate
python -m yanling.scenarios.embedded.run_persistent
```

启动后打开浏览器访问：**http://localhost:8764**

> 建议使用 `systemd` 或 `screen` 让园丁在后台持续运行。

<details>
<summary><b>使用 systemd 设置开机自启（Linux）</b></summary>

```bash
# 创建服务文件
sudo tee /etc/systemd/system/yanling.service << 'EOF'
[Unit]
Description=衍灵园丁
After=network.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/yanling
Environment=YANLING_NODE_ROLE=gardener
ExecStart=/home/你的用户名/yanling/.venv/bin/python -m yanling.scenarios.embedded.run_persistent
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
sudo systemctl enable yanling
sudo systemctl start yanling
sudo systemctl status yanling
```
</details>

---

#### 掌簿（NAS / 树莓派 / 低功耗设备）

掌簿是安全管家，专门管理密码、API 密钥等敏感信息。它资源占用极低，适合 24 小时运行的设备。

```bash
# 设置角色
export YANLING_NODE_ROLE=accountant

# 启动掌簿
cd ~/yanling
source .venv/bin/activate
python -m yanling.scenarios.embedded.run_persistent
```

启动后打开浏览器访问：**http://localhost:8764**

---

## 三、Web 面板使用说明

衍灵的每一台设备都自带 Web 管理面板，打开浏览器输入 `http://localhost:8764` 即可访问。

### 面板布局

面板分为两大区域：

**本机管理（左上角标签）**
- **概览** — 引擎运行状态、性能指标、当前 Tick 详情
- **记忆** — 衍灵记住了什么（工作记忆、短期记忆、长期记忆）
- **进化** — 衍灵的学习进度、性能趋势

**衍灵集群（右上角标签）**
- **集群管理** — 查看网络中所有衍灵节点的运行状态

### 概览页说明

| 区域 | 说明 |
|------|------|
| 顶部指标卡 | 总运行次数、已运行时长、任务成功率、平均响应时间 |
| 引擎状态 | 当前状态（运行中/已停止）、运行到第几轮、空闲次数 |
| LLM 模型 | 当前使用的 AI 模型名称，可点击"切换"更换 |
| 基线模型 | 内置保底小模型（TinyLlama），一键恢复 |
| 最近 Tick | 最近一次运行的详细信息 |
| 记忆系统 | 衍灵的记忆使用情况 |
| 进化系统 | 衍灵的学习进度和性能趋势 |

### 切换模型

1. 在概览页点击 **"切换"** 按钮（模型名称旁边）
2. 下拉菜单会列出所有可用模型，可用的前面有 ✓ 标记
3. 选择一个模型，点击 **"确认切换"**
4. 如果当前模型不可用，面板顶部会 ★ 推荐一个替代模型

### 恢复基线

如果 AI 模型出现问题（比如网络断了、API 密钥失效了），点击 **"恢复基线"** 按钮，衍灵会自动切换到内置的小模型（TinyLlama）继续运行。

---

## 四、多设备协同（可选）

如果家里有多台设备（比如 Mac Mini + Windows 笔记本），可以让它们组成一个衍灵集群。

### 前提条件

1. 每台设备都安装 ZeroTier（虚拟组网工具）
2. 至少有一台设备已加入 ZeroTier 网络

### 安装 ZeroTier

<details>
<summary><b>macOS</b></summary>

```bash
brew install --cask zerotier-one
```
</details>

<details>
<summary><b>Windows</b></summary>

1. 访问 https://www.zerotier.com/download/ 下载安装包
2. 安装后右键系统托盘图标 → "Join Network"
3. 输入网络 ID
</details>

<details>
<summary><b>Linux</b></summary>

```bash
curl -s https://install.zerotier.com | sudo bash
sudo zerotier-cli join 你的网络ID
```
</details>

### 加入集群

所有设备安装好衍灵并启动后，黑板服务器会自动发现彼此。打开任意一台设备的 Web 面板：

1. 点击 **"集群管理"** 标签
2. 如果其他设备在线，会以卡片形式显示
3. 绿色圆点 = 在线，灰色 = 离线

---

## 五、常见问题

### Q: 面板打不开（浏览器显示"无法访问此网站"）

- 确认衍灵正在运行（终端窗口没有关闭）
- 确认地址输入正确：`http://localhost:8764`（注意是 8764，不是 8080）
- 如果在本机访问，使用 `localhost`，不要用 `127.0.0.1`

### Q: Web 面板是空的，没有数据显示

- 引擎可能没有在运行。查看终端窗口是否有报错信息
- 刷新页面等待几秒，数据会自动更新

### Q: 显示"引擎未运行"

- 你的衍灵还没有启动。重启终端并重新运行启动命令
- 如果是因为空闲超时进入休眠，执行一次操作即可唤醒

### Q: 模型切换失败

- 查看该模型旁边是否有 ✗ 标记，有则说明该模型在当前设备不可用
- DeepSeek 云端模型需要联网和有效的 API 密钥
- 本地模型（oMLX/Ollama）需要启动对应的本地服务
- 如果都不行，点击"恢复基线"使用内置小模型

### Q: 如何更新衍灵？

```bash
cd ~/yanling
git pull                    # 拉取最新代码
source .venv/bin/activate
pip install -e ".[web]"    # 更新依赖
# 重新启动衍灵
```

### Q: 如何卸载衍灵？

```bash
# 删除衍灵文件夹即可
rm -rf ~/yanling
# （可选）删除 Python 虚拟环境
rm -rf ~/yanling/.venv
```

---

## 六、各角色资源占用参考

| 角色 | 内存 | 硬盘 | CPU | 典型功耗 |
|------|------|------|-----|---------|
| 灯塔（云端模型） | ~200MB | ~500MB | 低 | 3-10W |
| 管家 | ~100MB | ~300MB | 低 | 2-5W |
| 园丁（内容生产） | ~300MB | ~2GB | 中 | 5-15W |
| 掌簿 | ~80MB | ~200MB | 极低 | 1-3W |
| 基线模型（TinyLlama） | +~700MB | +~650MB | 仅推理时 | 额外 1-3W |

> 以上为估算值，实际占用取决于具体的任务负荷。

---

## 七、技术支持

- **问题反馈**：在 GitHub 提交 Issue
- **内测交流**：联系你的对接人加入飞书群

---

*衍灵 — 自主运行、自我进化的 AI 系统*

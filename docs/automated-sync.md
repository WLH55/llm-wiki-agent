# 自动化知识库同步指南

管理 LLM Wiki 的最佳方式是让它持续反映你的后台笔记系统。与其每次写新内容时手动导入文件，不如编排一个端到端的自动化流水线。

本指南概述了适用于本地 Mac/Linux 环境的生产级 cron/launchd 策略。

## 两步架构

LLM Wiki Agent 的导入是一个两步过程：
1. **同步到 `raw/`**：将文件从个人库/工具同步到代理的暂存区。
2. **批量导入**：对同步的目录触发 `tools/ingest.py`，将内容综合并编织到图谱中。

### 第一步：主编排脚本

在知识库根目录创建一个综合 shell 脚本（`daily-automated-sync.sh`）：

```bash
#!/usr/bin/env bash
set -uo pipefail

# 定义变量
LAB_DIR="$HOME/projects/active/personal-wiki-lab"
LOG_FILE="$LAB_DIR/automation-cron.log"
DATE=$(date "+%Y-%m-%d %H:%M:%S")

echo "=====================================================" >> "$LOG_FILE"
echo "[$DATE] 开始自动化知识库同步..." >> "$LOG_FILE"

cd "$LAB_DIR" || exit 1

# 1. 在这里运行你的个人库到 raw 的符号链接脚本
# 示例：./sync-raw.sh >> "$LOG_FILE" 2>&1

# 2. 使用你选择的 LLM 触发批量导入
export LLM_MODEL="gemini/gemini-3-flash-preview"
export GEMINI_API_KEY="AIzaSy..."  # 或 export OPENAI_API_KEY

echo "[$DATE] 批量导入 Markdown 文件..." >> "$LOG_FILE"
find raw/ -type l -name "*.md" -o -type f -name "*.md" | \
while read file; do 
    python3 tools/ingest.py "$file" >> "$LOG_FILE" 2>&1
done

# 3. 修复图谱上下文（自动解析断裂的语义链接）
echo "[$DATE] 修复断裂节点..." >> "$LOG_FILE"
python3 tools/heal.py >> "$LOG_FILE" 2>&1

echo "[$(date "+%Y-%m-%d %H:%M:%S")] 自动化同步完成。" >> "$LOG_FILE"
echo "=====================================================" >> "$LOG_FILE"
```

别忘了赋予执行权限：`chmod +x daily-automated-sync.sh`。

### 第二步：系统调度器（macOS launchd）

对于 macOS，`launchd` 比 `cron` 更加稳健。

在 `~/Library/LaunchAgents/com.personal-wiki-sync.plist` 创建 `.plist` 文件：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.personal-wiki-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/your-username/projects/active/personal-wiki-lab/daily-automated-sync.sh</string>
    </array>
    
    <!-- 每天凌晨 2:00 自动执行 -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- 如果错过了间隔，系统启动时也会运行 -->
    <key>RunAtLoad</key>
    <true/>

    <!-- 诊断日志 -->
    <key>StandardOutPath</key>
    <string>/Users/your-username/projects/active/personal-wiki-lab/daemon.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/your-username/projects/active/personal-wiki-lab/daemon.stderr.log</string>
</dict>
</plist>
```

加载守护进程：
```bash
launchctl load ~/Library/LaunchAgents/com.personal-wiki-sync.plist
```

### 自修复与健康监控
由于自动化在夜间静默运行，`daemon.stderr.log` 确保你能发现任何 API 故障。编排脚本包含 `tools/heal.py`，强烈推荐：它会无缝拦截并构建在一天中累积但从未被单独形式化的概念。

# dsh-session-repack

> 给 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（dsh）会话日志「放气」的小工具。
> **内容一个字不动，只换更省的分块方式。** 一条 40MB+ 的会话通常能压到 8~16MB。
>
> **适用于不想换掉「大肥鱼」初始会话的朋友们** —— 会话一直用同一条，文件肥了就重压一遍，不用换号、不用重新养。
>
> **本工具由 DSH 自行编写**：一个大肥鱼（DeepSeek Harness 智能体）给自己做的手术刀，
> 在自己身上试过、失败过、回滚过，才交到你手上。署名：**大肥鱼**。

[中文](#它解决什么问题) · [English summary](#english)

---

## 它解决什么问题

dsh 把每条消息、每次工具调用都**单独压成一个小块**追加到会话文件尾：

```
[块1: header] [块2: 一条消息] [块3: 工具结果] … （几万个块）
```

小块压缩率极差（约 1.5 倍），于是几百轮对话之后 `session.v4.jsonl.zstd` 能顶到 40MB+。
你会遇到：**打开会话变慢、GUI 卡顿、上下文没超但请求体过大被模型端拒（HTTP 400）**。

dsh 的校验代码只要求「第一个 frame 里正好一行 header」。所以可以安全地重排成：

```
[块1: header（1 行）] [块2: 其余全部（一个块）]
```

同样内容，压缩率约 8 倍。**压完逐行比对，不一致就不替换。**

## 实测数据（不要只看宣传）

| 会话 | 原始 | 重压后 | 比例 | 行数校验 |
|---|---|---|---|---|
| 日常聊天（工具调用少） | 44.1MB | **8.3MB** | 19% | 45538 行一致 ✔ |
| 管理会话（工具调用多） | 43.5MB | **16.5MB** | 38% | 59189 行一致 ✔ |
| 群聊（重复内容多） | 10.8MB | **1.7MB** | 16% | 10785 行一致 ✔ |

> 压缩率取决于你会话里「工具结果 / 重复提示词」占多少。工具调用越多，收益越小。

## 优点

- **内容零风险**：只改压缩分块方式；压完把两份都解成行数组做 `==` 比较，不一致就放弃这一份
- **不触发 dsh 的校验失败**：header 单独一帧，正好满足它的 `first frame is exactly one header line`
- **阈值保护**：默认只在文件 > 20MB 时动手，不会没事重启你的 dsh
- **先看不动**：`--dry`（只报告）、`--no-restart`（只生成 `.repacked` 文件）
- **替换前留备份**：`*.repack-bak-<时间戳>`
- **跨平台**：Windows / macOS / Linux（自动选 `taskkill` 或 `pkill`）
- **单文件**：`repack.py` 只有 200 行，只依赖 `zstandard`，没有别的黑魔法

## 缺点（这部分也请认真看）

- **治不了根**：dsh 依旧按「一条一块」追加，**几天后文件会重新长回去**。所以它必须是**周期性任务**，不是跑一次就完
- **不等于压缩上下文**：文件大小 ≠ 上下文长度。真正压上下文的是 dsh 自己的 `/compact`；这个工具只让磁盘上的日志变小
- **要重启 dsh**（自动模式下）：替换文件时 dsh 不能持有它。重启会让缓存失效、正在跑的会话断一下
- **依赖 dsh 当前的日志格式**：以后 dsh 若改掉 zstd 分块或校验方式，本工具会失效。**升级 dsh 之后先跑 `--dry`，跑完确认会话还能正常打开**
- **不适合在磁盘空间告急时当"清理工具"**：它不删任何历史，只是重新打包

## 安装

```bash
pip install zstandard
```

只需要 Python 3.9+。把 `repack.py` 放到任意目录即可，无其他依赖。

## 用法

```bash
# 1) 先看看哪些会话超阈值（默认 20MB），什么都不改
python repack.py --dry

# 2) 最保守：只生成 <文件>.repacked，自己挑时间手动换
python repack.py

# 3) 全自动：停 dsh → 替换 → 再启动
python repack.py --restart --exe "C:\path\to\DeepSeek Harness.exe"
```

| 参数 | 说明 |
|---|---|
| `--threshold-mb 20` | 超过多少 MB 才处理（传 0 = 全部重压，测试用） |
| `--dry` | 只报告，不动任何文件 |
| `--no-restart` | 只生成 `*.repacked` |
| `--restart` | 允许停/启 dsh |
| `--level 10` | zstd 压缩等级（10 够用；19 更慢更小） |
| `--dsh-home ~/.dsh` | dsh 数据目录 |
| `--exe "…"` | dsh 可执行文件路径（Windows 重启用；不给则用 `dsh web`） |

## 挂成计划任务

**Windows**

```bat
install-windows.bat
```

会装依赖、自动找 `DeepSeek Harness.exe`、创建每天 04:00 的计划任务 `DshSessionRepack`。

**Linux / macOS**

```bash
bash install-unix.sh
```

写入 crontab（每天 04:00）。卸载：`crontab -l | grep -v repack.py | crontab -`。

## 常见问题

**Q：压完之后我的会话会不会少东西？**
不会。工具在替换前会把新旧两份都解压成行数组逐个比较；不一致就跳过这一份，原文件不动。

**Q：为什么不能一次压成一个块？**
我试过——dsh 直接报 `corrupt Zstandard session log: first frame is not exactly one header line`，会话打不开。**必须让 header 单独成一帧。**

**Q：压完文件又涨回去了怎么办？**
正常。这就是它必须定时跑的原因。一天一次（04:00）通常够。

**Q：跑完 dsh 打不开会话了怎么办？**
把同目录下最新的 `session.v4.jsonl.zstd.repack-bak-<时间戳>` 改回 `session.v4.jsonl.zstd` 即可。

**Q：文件变小了，为什么 token 没变少？**
因为两个东西：文件是磁盘上的历史流水账，上下文是这一轮实际喂给模型的部分。想省钱要管上下文（`/compact`、压缩阈值），不是管文件。

## 原理备注

zstd 允许多个 frame 顺序拼接，解压时自动连起来。dsh 打开会话时只校验第一个 frame 的内容是不是「正好一行 header」。
所以「header 一帧 + 其余一帧」既满足它的校验，又能拿到整块压缩的比率。

<a name="english"></a>
## English

`dsh` (DeepSeek Harness) appends one tiny zstd frame per record, so a long session log balloons to 40MB+
(compression ratio ~1.5x) and can make session loading slow or cause oversized-request HTTP 400s.

`repack.py` rewrites the log as **two frames**: the header line alone, then everything else in one frame.
dsh's validation only requires the first frame to contain exactly one header line, so this is accepted —
and gets ~8x compression. Content is verified line-by-line before replacing anything.

```bash
python repack.py --dry                 # report only
python repack.py --restart --exe "…"   # stop dsh, replace, start dsh
```

**Pros**: content untouched (verified), header-frame trick satisfies dsh, threshold-gated, dry-run, timestamped backups, cross-platform, single file.
**Cons**: doesn't fix the root cause (file regrows — run it periodically), doesn't reduce context/token cost, requires a dsh restart in automatic mode, and may break if dsh changes its log format.

## License

MIT

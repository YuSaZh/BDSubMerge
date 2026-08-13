# BDSubMerge 用户指南

本文描述当前已实现的 pre-alpha 工作流。GUI 仍在集成中；CLI 调用相同的应用服务，
适合进行可复现检查。

## 1. 输入与扫描

BDSubMerge 可接受光盘容器目录、`BDMV` 目录、`index.bdmv`、`PLAYLIST` 目录或单个
`.mpls` 文件。扫描会定位实际的 `index.bdmv`、`PLAYLIST`、`CLIPINF` 和 `STREAM`。
所有 BDMV 数据始终只读。

```powershell
bdsubmerge scan "D:\Anime\Title\BDMV" --json
```

从原盘上层目录扫描时可使用 `--max-depth N`。可选的 `--subtitle-duration-90k` 和
`--subtitle-count` 会改进推荐。时长采用 90 kHz 整数 ticks，一秒为 90,000 ticks。

某一 MPLS 解析失败不会终止整个扫描；该播放列表会标记为不可用并报告原因。

## 2. 播放列表推荐

每个可用 MPLS 都会得到确定性分数、置信度和推荐原因。评分考虑总时长、PlayItem 和
章节数、唯一/重复 Clip、极短片段、M2TS/CLPI 引用缺失、多角度、字幕累计时长以及
预期分集数。系统不会仅按“最长 MPLS”自动决定主播放列表。

```powershell
bdsubmerge inspect "D:\Anime\Title\BDMV\PLAYLIST\00001.mpls" --json --verbose
```

`--verbose` 包含 PlayItem、章节标记、警告、错误和 Timeline Fingerprint。只有 Clip ID、
IN/OUT 时间和所选角度的完整序列相同，两个 MPLS 才属于时间线等价。

对于 AC-10，多条非等价 MPLS 不能共用一个 JRiver `index.ass` 时间线。必须指定唯一的
JRiver 主时间线，其他时间线使用 MPLS 同名或自定义输出。

## 3. 字幕输入

一个合并任务只能使用同一字幕类型：

- ASS 或 SSA 文本字幕；
- SRT 文本字幕；
- Blu-ray PGS SUP 字幕。

不得在一个任务中混合 ASS 与 SRT，也不得混合文本字幕与 SUP。文本解码支持 UTF-8、
UTF-8 BOM、UTF-16 LE/BE、GB18030 和 Shift-JIS；传统编码存在歧义时必须明确指定。
SRT 默认以 UTF-8 BOM 输出。

ASS/SSA 会保留 Dialogue、Comment、声明的 `Format` 字段顺序、样式、解析后的
`\rStyle` 引用、Script Info 冲突信息、Aegisub Extradata、字体、图形和未知 section。
未知或冲突数据会进入报告，不会静默丢弃。

## 4. 映射与边界

候选边界来自播放列表起止、PlayItem 边缘和章节标记。整数优化器将有序字幕映射到
单调递增区间，并给出置信度和原因。字幕最后一句早于区间结束是正常情况，明显超出
目标区间的惩罚更高。

低置信度结果必须人工检查。保存的映射包括：

- 字幕 ID 和顺序；
- 起止边界 ID 及精确 90 kHz 时间；
- 90 kHz 手动微调；
- 锁定状态、置信度和警告。

项目恢复时会保留用户边界和精确映射时间。锁定映射必须复现原区间和微调，不允许
静默重新求解成不同结果。

## 5. 预检

写入前会检查源文件指纹、播放列表时间线、映射完整性和顺序、输出扩展名、目录、
文件冲突、重复目标、输入/输出重合及 JRiver 命名。结果分为错误、警告和信息。

任一错误会阻止所有输出。警告会保留在验证和 dry-run 结果中，但实际写入前必须在 GUI
明确确认，或在 CLI 传入 `--accept-warnings`；信息无需确认。多目标任务先完成整体预检，
之后才会统一暂存、验证并提交；失败时执行回滚。

```powershell
bdsubmerge validate "D:\Projects\Title.bdsm.json" --json --verbose
bdsubmerge merge "D:\Projects\Title.bdsm.json" --dry-run --json
bdsubmerge merge "D:\Projects\Title.bdsm.json" --accept-warnings --json
```

`validate` 会重建计划和输出预检。`merge --dry-run` 继续执行 prepare/execute 检查并报告
将写入的内容，但不会创建输出文件。

## 6. 输出模式

- **JRiver：**严格输出到实际 BDMV 的 `index.ass`（或对应格式扩展名），路径根据发现的
  `index.bdmv` 计算。禁止自动改名，一个 BDMV 只能配置一个 JRiver 主目标；
- **MPLS 同名：**`<BDMV>/PLAYLIST/<playlist_stem>.<ext>`，可选语言后缀；
- **原盘目录同名：**在光盘容器父目录或指定目录生成 `<disc-name>.<ext>`；
- **模板：**支持 `{disc_name}`、`{playlist}`、`{playlist_stem}`、`{index_stem}`、
  `{language}`、`{format}` 和 `{volume}`；
- **完整路径：**直接指定最终文件路径。

冲突策略包括 `abort`、`overwrite`、`backup` 和 `auto_rename`，并受各输出模式限制。
默认是安全的 `abort`。源字幕和 BDMV 媒体文件都不能作为输出目标。

## 7. 项目保存、恢复与重定位

`.bdsm.json` schema v1 保存 BDMV/index/MPLS 定位与元数据指纹、播放列表 Timeline
Fingerprint、有序字幕及编码、边界、锁定映射和微调、输出/冲突策略及 UI notes。共享
非根目录树中的路径优先使用相对形式，同时保留绝对恢复提示。

项目保存使用同目录临时文件，执行 flush、`fsync` 后原子替换。加载时 index/MPLS/字幕
会标记为 `unchanged`、`changed` 或 `missing`；BDMV 目录只检查是否存在，生成新的
`index.ass` 不会被误判为原盘源变化。

changed 或 missing 会阻止 CLI 验证和合并。确认文件身份后，应显式重定位并刷新指纹。
GUI 打开存在未解决输入的项目时，会在扫描 BDMV 或加载字幕之前列出全部项目源。逐项
定位 BDMV 目录或源文件；指纹精确匹配会直接接受，changed 文件则必须明确确认，且
确认框默认选择“否”。只有全部源、保存的 MPLS 时间线和字幕加载均验证成功后，项目
JSON 才会原子更新；取消或任何失败均保留当前工作区和原项目文件不变。

CLI 保持非交互：`validate` 和 `merge` 遇到 changed 或 missing 会报告并停止。请先在 GUI
完成重定位，再重新执行 CLI 命令。匿名示例
[`examples/minimal.bdsm.json`](../examples/minimal.bdsm.json) 仅展示结构，其中的
占位源文件必须先重定位，不能直接用于合并。

## 8. CLI 参考

公共选项可放在子命令前或后：

- `--json`：输出一个 JSON envelope；
- `--dry-run`：不写入合并结果；
- `--verbose`：包含详细结构和诊断；
- `--version`：显示包版本。

命令：

```text
bdsubmerge scan <path> [--max-depth N] [--subtitle-duration-90k TICKS] [--subtitle-count N]
bdsubmerge inspect <mpls> [--max-depth N]
bdsubmerge plan <project.bdsm.json>
bdsubmerge validate <project.bdsm.json>
bdsubmerge merge <project.bdsm.json> [--dry-run] [--accept-warnings]
  [--report <path>] [--report-format json|text]
  [--report-collision abort|overwrite|backup|auto_rename]
```

`plan` 只显示持久化项目，不执行合并；`validate` 重新加载输入、复现锁定映射并执行
输出预检；`merge` 才执行事务输出。指定 `--report` 后，UTF-8 JSON 或文本报告会与字幕
输出一起预检，并在同一个原子事务中提交。报告不能写入 BDMV 树、输入文件、字幕输出
或项目文件本身。

运行日志是平台用户数据日志目录中的有界 JSON Lines 文件（Windows 默认为
`%LOCALAPPDATA%\BDSubMerge\logs`）。日志包含版本、路径、映射/输出诊断和异常堆栈帧，
但不会记录字幕正文或异常消息。

JSON 顶层格式固定为：

```json
{
  "command": "validate",
  "data": {},
  "exit_code": 0,
  "issues": [],
  "ok": true
}
```

退出码：

| 代码 | 含义 |
| ---: | --- |
| 0 | 成功 |
| 2 | CLI 参数错误 |
| 3 | 输入或项目 JSON 无效 |
| 4 | 验证或预检失败 |
| 5 | 执行失败 |

## 9. Windows Artifact

GitHub 的 **Package Windows** workflow 在 `BDSubMerge-windows-x64` artifact 中生成
`BDSubMerge-windows-x64.zip` 和对应 SHA-256 文件。校验哈希后完整解压 onedir 包，并保持
`_internal`、`LICENSE`、`LICENSES` 和 `THIRD_PARTY_NOTICES.md` 与程序目录结构不变。
workflow 会清除 Python 环境变量，从含中文和空格的路径启动最终 ZIP 中的程序进行烟测。

在明确发布 release 前，该 artifact 仍是开发构建。Windows CI 会创建隔离的临时 SMB
共享，并在真实 UNC 路径上验证扫描、预检和原子写入；商业原盘夹具广度和干净的
Windows 10/11 桌面仍属于独立验证项。

## 10. 安全与开发规则

- 永远不修改 BDMV 源结构；
- 不静默覆盖，写入前必须显示并预检完整目标；
- 除非用户主动启用未来的调试功能，否则不记录字幕正文；
- 不包含遥测、网络上传、在线字幕下载或自动更新；
- 仓库贡献者禁止本机构建、测试、lint、类型检查、安装依赖或打包，必须推送后使用
  GitHub Actions 验证。

当前真实验证缺口是实际 MPLS/SUP fixture 覆盖广度和干净的 Windows 10/11 桌面。

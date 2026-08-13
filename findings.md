# 发现与决策

## 需求
- 任务书 9.3 要求每个源字幕可查看文件名、格式、编码、事件数、样式数、最早开始、原始/有效结束、PlayRes、字体/图形附件、Aegisub Extradata 与警告数量；19.3 要求播放列表双击查看结构；19.5 要求输出区域显示完整路径、编码、冲突策略、备份、输出格式、预计事件/样式数量和警告摘要。
- 工具面向 Windows 11，输入 BDMV/PLAYLIST/MPLS/index.bdmv，输出外置 ASS/SSA/SRT/SUP。
- 任务书要求自动播放列表推荐、分集字幕映射、可视化时间线、多输出目标、项目复现和 CLI。
- UI 默认简体中文并支持英文，耗时任务必须在后台运行。
- 本机禁止构建、测试、lint、类型检查、依赖安装和打包；本机只做源码检查、静态搜索、Git 操作与 `git diff --check`，所有执行型验证必须提交并推送到 GitHub Actions。

## 研究发现
- 2026-08-13 继续开发时，`main` 与 `origin/main` 均为 `251424a`，工作树除 `task_plan.md`、`findings.md`、`progress.md` 外无未提交文件；`application/display_models.py` 已有 Qt 无关的播放列表/字幕详情投影，但 GUI 尚未接入，下一批必须以任务书原文和现有 UI 状态机为准补齐。
- 已有 `format_playlist_structure` / `format_subtitle_details` 包含英文硬编码；双语 GUI 不应复用其最终文本，而应消费对应 dataclass 后在 UI 层翻译和格式化。
- 输出目标表原先只有 ID、模式、路径和冲突策略，任务书 19.5 还要求编码、是否备份和输出格式；本批扩为 7 列，并让路径列独占伸缩空间，便于同时扫描多个目标。
- 字幕表支持重排，详情必须通过表格 `UserRole` 中的路径定位 `SubtitleAsset`，不能直接以可见行号索引初始资产；源级 warning 可通过 `ApplicationIssue.source` 精确归属。
- GitHub 仓库为 `YuSaZh/BDSubMerge`，远端使用 SSH；Git/GitHub 操作应直接调用本机现有凭据，不启动浏览器登录。
- 当前已推送 M5 核心远程验证：run `31627068738` 的 Ubuntu、Windows、源码包任务全部成功。
- M1-M4 的领域逻辑与输出边界已经实现，当前缺口集中在 M5 集成、CLI、UI、打包与完整验收。
- Shinya 官方导入为 `shinya.bd.MoviePlaylistFile`；匿名 MPLS0200 二进制夹具固定了
  `0.2a1`（上游 commit `53998916`）的真实解析字段契约。
- SUP 时长现在优先采用“可见 PCS 之后的零对象 PCS”清屏 PTS；没有可靠清屏段时回退到最大 packet PTS 并标记为估算。
- 当前 PGS 平移按任务书将 packet 的 PTS/DTS 字段统一加偏移，包括数值为零的字段；如真实夹具显示零 DTS 是缺省语义，再以契约测试调整。
- BDMV 目录只做存在性检查；目录 mtime 会被合法生成的 `index.ass` 改变，因此输入变化判断以 index、MPLS 和字幕文件指纹为准。
- 输出目标可能尚不存在，恢复时必须无条件优先项目相对路径；源文件则只有相对候选存在时才优先，二者使用独立解析 API。
- 用户边界与自动边界同刻时会被规范化为一个候选；应用层需把持久化锁的原始边界 ID 映射到规范 ID，避免恢复失败。
- 当前 GUI 批次已将应用层 `MappingResult` 投影为时间线分集与实际内容区间，接通映射表/时间线双向选择，并让边界下拉或拖动生成 `MappingLock` 后按 revision 重新预检；该结论仍需 GitHub Actions 的 Qt 测试验证。
- run `31668089029` 的源码包和 Ubuntu/Windows Ruff 已通过；两平台 Mypy 同样因 3 处局部变量类型收窄失败，Pytest 尚未运行。
- GUI 恢复 offset 过去经 `// 90` 保存为毫秒再 `* 90`，会丢失非整毫秒 tick；内存态必须直接保存原始 90 kHz tick，毫秒只作为控件显示/输入单位。
- GUI 编辑期间还需保证：运行中预检进入 pending、解锁清除人工 offset、非法时间线拖动回滚、任务期目录 drop 不改变状态，并使保存态反映当前锁与 offset。
- commit `bca41f6` 的 run `31669097224` 已在源码包、Ubuntu/Windows Ruff、Mypy、Pytest 和真实 Windows UNC 上全部通过，精确 tick 与 3 个 Mypy 根因已闭环。
- 历史 CI 的 UI 截图步骤使用 `runner.os == 'Ubuntu'`，实际一直 skipped；当前批次改为 `Linux`，下一次 run 必须下载 PNG 并人工审查后才能声称截图验收完成。
- 当前异步一致性批次采用应用状态驱动的整行重排，不依赖 Qt 对含 `QComboBox` 的 `InternalMove` 行搬移；项目恢复任务失败/取消会清理 pending 状态，任务失败不会再显示完成。
- UI 截图必须作为独立 artifact 使用精确 PNG 路径和 `if-no-files-found: error`；上传整个已有 JUnit/coverage 的 `reports/` 目录不能证明截图存在。Ubuntu 截图还需显式安装 CJK 字体，避免中文界面依赖 runner 的偶然字体集合。
- commit `38c3d78` 的 run `31672669445` 已完成远程闭环：Ubuntu 230 passed、2 skipped、82.93%，Windows 232 passed、82.92% 且真实 SMB/UNC 通过；四态截图 artifact `9170299987` 的文件哈希与日志一致，人工审计无重叠、截断或 CJK 缺字。
- 当前工作树在绿色基线之后已有实际进度回调、字幕发现/加载应用服务和 UI 任务桥接的未提交源码；这些改动尚无对应测试提交或 Actions run，必须作为独立在研批次审计，不能视为已验证功能。
- 当前 goal 已处于 active；执行边界以仓库级 `AGENTS.md` 为准，GitHub Actions 是唯一执行性验证环境，本机环境缺项不构成需要补装的开发阻塞。
- 2026-08-13 再次实测本机凭据：显式使用 `C:\Users\Hanam\.ssh\config` 与 `known_hosts` 可读取 `git@github.com:YuSaZh/BDSubMerge.git`；`gh auth status` 显示活动账号 `YuSaZh`、SSH Git 协议和 `repo` scope。沙箱内不能直接读取用户 SSH 配置，外部 Git 对沙箱所有权仓库需使用单次 `safe.directory`，两者都不需要更改全局 Git 或网页登录。
- 当前未提交实现已让 `ServiceTask` 透传嵌套进度，并让 GUI 显示详情；但应用层目前只有字幕发现/加载报告中间进度，扫描、预检、合并等长任务是否有足够的阶段与详情仍需逐一审计。
- 当前未提交批次还把目录拖放的字幕发现移入应用服务，并新增项目扫描失败处理；现有 `tests/` 尚无对应未提交变化，必须补足服务、取消、进度和 GUI 回归测试后才能推送验证。
- 静态审计确认 `application/display_models.py` 已有播放列表结构和字幕详情投影，但 GUI 未调用；预检摘要也只显示路径和 issue，未显示任务书要求的预计事件数、样式数和警告摘要。阶段 5 对这三项的完成标记已撤回。
- 新项目打开必须两阶段提交：扫描失败时旧工作区和旧 `project_path` 均保留；扫描成功即解除旧项目关联；只有字幕恢复完整成功才绑定新项目路径，后续失败或缺失时强制另存为。
- run `31674853072` 的源码包、Ubuntu/Windows Ruff 与 Mypy 均通过；两平台 Pytest 唯一失败均为 `test_adding_directory_preserves_manual_order_and_appends_naturally` 的 `load_ordered` 测试替身未接受新增 `cancellation_check` 关键字。Ubuntu 为 254 项中 1 失败、2 跳过，Windows 为 254 项中 1 失败；Windows 真实 SMB/UNC 建立和清理正常，截图因 Pytest 失败而跳过。
- commit `251424a` / run `31675293315` 已闭环实际任务进度批次：源码包、双平台 Ruff/Mypy/Pytest、真实 Windows SMB/UNC 和四态 UI 截图均通过。JUnit 为 Ubuntu 254 项（2 skipped）和 Windows 254 项；coverage XML 行覆盖率分别为 87.05% 与 87.03%，终端综合覆盖率为 83.31%。四张截图哈希互异，人工审计无重叠、截断或 CJK 缺字。
- 当前详情批次已静态补齐播放列表结构、源字幕详情、输出目标完整字段，以及预计事件/样式/警告摘要；未跟踪新文件不会出现在普通 `git diff` 中，提交前必须显式读取并在暂存后用 `git diff --cached` 复核。
- commit `64e22a3` / run `31679107948` 已闭环详情与输出摘要批次：源码包、双平台 Ruff/Mypy/Pytest、真实 Windows UNC 和 Linux 四态截图矩阵全部通过。JUnit 为 Ubuntu 261 项（2 skipped）和 Windows 261 项；coverage XML 行覆盖率为 87.06%/87.04%。四张截图哈希互异，人工审计无重叠、截断或 CJK 缺字，完整 7 列输出摘要与事件/样式/警告统计均可见。
- `64e22a3` 的 Windows Package run `31679478339` 已通过 x64 onedir、许可证闭包、ZIP/SHA256、中文空格路径解压和无 Python 环境 EXE 烟测。artifact `9172908967` 包含 57,029,081 字节、314 个条目的 ZIP，SHA256 `662078ec309a867a5e443e12899c5290e2910e1f21f33f3d40fbae08e6265f2a` 与清单一致；它仍是 `0.1.0.dev0` 基线包，不是 1.0 最终候选。
- 发布前静态审计确认输出目标目录可被 collision 流程误处理、业务写入失败可被 GUI 显示为完成、普通会话未复核加载时源指纹。本批同时在共享应用/输出层修复，确保 CLI 与 GUI 使用同一安全契约；warning 确认和项目重定位仍为后续独立批次。
- commit `e5ae7b5` / run `31681278331` 已闭环上述源指纹、输出目标和 GUI 终态修复：源码包、Ubuntu/Windows Ruff、Mypy、Pytest、真实 Windows UNC 和 Linux 四态截图矩阵全部成功，现为远程绿色基线；Windows Package 仍需在统一 `1.0.0` 的最终候选上重新验证。
- 任务书 18 节的严重度契约要求 error 阻断、warning 明确确认后输出、info 无需确认；当前应用层 `PreparedMerge.ready` 已阻断 error，GUI 只需对 ready 状态中的 warning 增加默认 No 且 ESC 为 No 的双语确认，不改变 CLI 和无 warning 流程。
- commit `615d955` / run `31682267166` 已闭环 warning 明确确认：源码包、双平台 Ruff/Mypy、Ubuntu 278 passed / 2 skipped、Windows 280 passed、真实 Windows UNC 和四态截图矩阵全部成功；coverage XML 行覆盖率为 87.21%/87.19%。
- `615d955` 的绿灯只证明 GUI 在调用 execute 前询问；共享 `MergeApplicationService.execute()` 尚未强制确认，CLI 也曾静默传入低置信度接受标志。门禁必须下沉到应用服务，并由 GUI 确认结果和 CLI `--accept-warnings` 显式穿透，才能满足分层契约且不可被其他调用者绕过。
- 共享 warning 门禁批次的主路径已静态确认：`prepare()` 汇总 playlist、subtitle、低置信度、merge 与 output warning，`execute()` 仅在真实写入且 warning 未接受时返回 `warnings_not_accepted`，dry-run 保持零写入成功。全部 `ExecuteMergeRequest` 调用已逐项核对：overwrite、SUP 估算与低置信度接受分支显式确认；AC-06 的 auto-rename 仅产生 info，保持默认拒绝 warning 并新增严重度回归断言。
- 共享 prepare 接管 playlist/subtitle warning 后，CLI 成功路径仍同时拼接 scan/inspect/subtitle preliminary issues，可能让同一诊断重复出现；CLI 最终汇总现按完整 `CliIssue` 保序去重，既保留 scan 独有诊断，也避免 validate 和 merge dry-run 重复展示。
- commit `8fd25a7` / run `31685081960` 已闭环共享 warning 门禁：源码包、双平台 Ruff/Mypy/Pytest、Windows 真实 UNC 和 Linux 四态截图矩阵全部通过。JUnit 为 Ubuntu 288 项（2 skipped）和 Windows 288 项，coverage XML 行覆盖率为 87.54%/87.52%；artifacts `9175097451`、`9175090247`、`9175089638`、`9175057242` 均完整，四张截图哈希互异且目视无重叠、截断或 CJK 缺字。

## 技术决策
| 决策 | 理由 |
|------|------|
| 项目拥有 ASS/SRT/PGS 解析与序列化模型 | 避免第三方内部模型泄漏到领域层 |
| Shinya 通过单一适配器隔离 | 第三方字段变化只影响边界层 |
| 映射使用确定性有序非重叠动态规划 | 同一输入应得到稳定、可解释结果 |
| 项目文件保存相对路径并保留绝对恢复提示 | 兼顾可迁移性和源文件重定位 |
| CI 覆盖 Ubuntu 与 Windows | Linux 快速发现问题，Windows 验证目标平台 |

## 已知风险
- 已有由规范二进制布局构造并经真实 Shinya 解析器读取的匿名 MPLS 夹具；复杂商业盘
  与更多真实 SUP 样本仍需持续扩展。
- Windows/UNC 路径行为只能由 Windows GitHub runner 验证。
- PySide6 UI 源码已实现；仍需 GitHub Actions 验证严格类型、无头 Qt 事件行为和截图布局。
- Windows CI 将临时创建 runner 本机 SMB 共享，验证真正的 UNC 原子写入后立即清理。
- Windows onedir 包保留独立 Qt DLL，并收集实际 wheel 的 LGPL/第三方许可证与源码入口。

## 外部状态
- 2026-08-13 已在本机用户凭据上下文验证：Git SSH 可读取
  `git@github.com:YuSaZh/BDSubMerge.git`，远程 `main` 为 `e5ae7b5`；`gh` keyring 中
  `YuSaZh` 账号有效、使用 SSH 且具备 `repo` 权限。无需浏览器登录或新增本机开发环境。
- GitHub Actions run `31627068738`：M5 核心在 Windows、Ubuntu 与 source distribution 全部成功。
- GitHub Actions run `31630779273`：source distribution 成功；Ubuntu 与 Windows
  均只在 Ruff 阶段因同一组 16 项诊断失败，后续 Mypy、Pytest 和 UI 截图未执行。
- GitHub Actions run `31665885218`：提交 `1ca58d6` 的 Ubuntu、Windows、真实 UNC 与
  source distribution 全部通过，是当前未提交 GUI 映射批次的绿色基线。
- Ruff 修复提交 `f8c0552` 已推送；run `31659484298` 将诊断缩小为 2 项
  确定性排序问题，两个平台结果一致。
- Codex 沙箱的 Windows OpenSSH 默认解析到 `C:\Users\CodexSandboxOnline\.ssh`，会导致
  GitHub 主机密钥校验失败。Git 操作必须显式使用 `C:\Users\Hanam\.ssh\config` 和
  `C:\Users\Hanam\.ssh\known_hosts`，从而调用用户现有 SSH 凭据。

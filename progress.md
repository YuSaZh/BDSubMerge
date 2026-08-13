# 进度日志

## 会话：2026-08-14（v1.0.2-beta.1 测试版发布）

### 预发布准备
- **状态：** in_progress
- 用户要求发布 `v1.0.2-beta.1`；沿用已完成的发布后修复，并恢复端到端发布闭环。
- Python 项目/EXE 使用 PEP 440 版本 `1.0.2b1`，Git tag、ZIP 和 Release 展示使用 SemVer
  `1.0.2-beta.1`；Windows 工作流负责显式映射和一致性校验。
- 已补充双语测试版下载说明、Changelog 和内容完整的 Release notes；`v1.0.1` 继续标为稳定版。
- 本机聚焦回归 82 passed；完整回归 330 passed、2 deselected、coverage 84.86%。两项仅依赖
  GitHub Actions 创建的临时 Windows SMB/UNC 共享；Ruff 与 64 个源码文件的严格 Mypy 全部通过。
- 成功构建 `bdsubmerge-1.0.2b1` sdist/wheel，wheel 包含中英文翻译资源；PyInstaller 6.22.0
  成功生成 Windows onedir。
- 本机最终 ZIP 为 `BDSubMerge-1.0.2-beta.1-windows-x64.zip`，54,333,527 字节，SHA-256
  `764640fc4c8c261ce5b24966026fecc9d2aaa6cc8a5bae33f89c28d5caf79e74`。包内共 283 个条目，
  根目录仅有 EXE、项目 `LICENSE` 和 `_internal`，无根 `LICENSES/` 或 `THIRD_PARTY_NOTICES.md`。
- 清空 Python 环境并收窄 PATH 后，最终 EXE 的 `--expect-version 1.0.2b1` 烟测退出 0；中文
  浅色截图为 2160x1500、106,123 字节，目视确认字体、布局和本批 UI 修复正常。

## 会话：2026-08-14（v1.0.1 发布后反馈，不发版）

### 表格、边界列表、时间线与映射诊断
- **状态：** in_progress
- 用户确认本批先解释置信度与 `event ends at or before zero`，再修复 UI/本地化/映射体验，明确不发版。
- 当前置信度成本包含字幕与区间时长差、过长 8 倍惩罚、边界置信度、短区间和估算时长惩罚；此外第二优局部候选成本差不超过参考时长 3% 时会无条件判低。30 ms 时长差本身不足以判低，密集章节产生的近似候选歧义是主要嫌疑。
- `event ends at or before zero` 表示应用最终 offset 后事件结束 tick 不大于 0，合并器按设计丢弃；大量出现意味着源文件包含较多零点前事件，或整体负向偏移把事件推到零点前。
- 中文目录已有 `issue.event_dropped_before_zero`，但应用层投影为 `merge_event_dropped_before_zero`，UI 使用完整码查找导致中文漏匹配，需规范化阶段前缀后再查翻译。
- 截图确认表格长文件名仍过早省略、边界 popup 沿用单元格宽度而截断、时间线缩放后文字被水平拉伸。
- 已实现首批修复并运行 75 项聚焦测试全部通过、Ruff 通过；严格 Mypy 发现新增 issue 分组键将可空 `source` 标成必填字符串，已按模型契约改为 `str | None` 后继续验证。
- 首轮完整测试使用了旧 AC-02 节点路径，未实际 deselect 当前的两项环境测试；结果为 329 passed、2 failed、coverage 84.88%。两项失败分别是受限本机访问故意不存在 UNC 路径返回 `WinError 5`，以及未提供 CI 临时 SMB share；Ruff 与 64 模块严格 Mypy 均通过。已通过 collect-only 确认当前精确节点并重新执行。
- 完成修复：字幕文件列装载后按最长内容扩宽且仍保持 Interactive；边界 combo popup 独立按最长“章节 ID + 时间”加宽并禁用省略；时间线全部文字忽略 view transform，横向滚轮缩放不再拉伸字形。
- `merge_`、`output_`、`report_` 阶段前缀诊断会回退到基础中文键；零点前事件中文说明明确为“应用时间偏移后”。相同严重度、代码、消息和来源的重复 issue 在摘要、确认框和错误详情中合并为一行 `(xN)`，底层 warning 数与 merge report 计数不变。
- 置信度歧义只在当前成本至少达到 medium 阈值时才升级为 low；23:39.930 对 23:39.960 的 30 ms/2700 ticks 样例为 score 100、high。新增保护测试确认约 10% 误差且候选接近时仍为 low。
- 最终局部回归 79 passed；完整本机回归 330 passed、2 deselected、coverage 84.86%，两项仅为 CI 临时 SMB/UNC 环境。Ruff、64 模块严格 Mypy、`git diff --check` 均通过。
- 原生 Windows 中文截图为 2160x1500、168,264 字节，目视确认 CJK 字体、布局、字幕表和时间线正常。本批按用户要求未改版本、未提交、未推送、未打 tag、未发版。

## 会话：2026-08-13（v1.0.1 用户反馈）

### 反馈收集与实现审计
- **状态：** in_progress
- 已读取三张用户截图并确认字幕表高度不足、文件名截断、序号重复和未启用报告配置仍占空间四项可见问题。
- 本批将同时处理许可证打包、双语 README、诊断中文化、时间线滚轮缩放、边界章节显示和 v1.0.1 发布说明。
- 按用户最终规则和仓库 `AGENTS.md`，本机固定使用 `py -3.12`，允许安装 Python 包并执行测试、Ruff、Mypy、构建和打包；需要新增非 Python 环境的验证交给 GitHub Actions，最终推送提交按精确 SHA 审计。
- 已定位 GUI 实现：字幕表默认伸缩策略阻止自由列宽、左侧 vertical header 与“序号”数据列重复、报告配置只禁用未隐藏、边界 cell 与下拉均使用同一完整标签。
- 已定位时间线实现：完整时长直接映射视口，需新增整数 tick 可见窗口与滚轮锚点缩放；应用核心仍保持 90 kHz 整数 tick。
- 已定位打包实现：`.github/workflows/package-windows.yml` 显式创建并验证 `LICENSES/`；v1.0.1 将只复制和验证项目根 `LICENSE`。
- 一次只读命令误猜工作流为 `.github/workflows/package.yml`，实际文件是 `package-windows.yml`；已按真实路径继续，未产生写入或执行项目代码。
- GUI/翻译局部回归为 70 passed；全仓 Ruff、64 模块严格 Mypy、328 passed/2 deselected、84.76% coverage 和 `1.0.1` sdist/wheel 均通过。两项 deselect 仅为 CI 创建临时 Windows SMB/UNC 共享的 AC-02。
- 本机 PyInstaller 6.22.0 已成功生成 Windows onedir。首次把 ZIP 压缩和内容检查并行执行时，检查在压缩完成前读取文件而得到 `FileNotFoundError`；压缩随后成功，改为串行审计，不重复该竞态方式。
- 首次调用 UI 截图脚本误用了不存在的 `--output` 参数；脚本要求目标路径作为位置参数，未生成截图或修改源码，已按真实 CLI 更正。
- 自动枚举诊断码时发现 7 个播放列表选择相关错误/警告码缺少中文说明，已补齐并保留原始技术信息作为附注。
- 最终本地源码门禁通过：328 passed、2 deselected、coverage 84.77%，Ruff、64 模块严格 Mypy、73 个静态诊断码中文目录完整性和 `git diff --check` 全部通过。
- 最终 Windows onedir/ZIP 审计通过：283 个条目、54,332,705 字节，EXE、双语资源和项目 `LICENSE` 存在，`LICENSES/` 与 `THIRD_PARTY_NOTICES.md` 不存在；清空 Python 环境后的 1.0.1 烟测退出 0。
- 最终 EXE 中文浅色截图为 1440x1000、106,123 字节；人工确认 CJK 字体完整、字幕区默认增高、序号不重复、报告选项折叠、缩放状态可见且无重叠/截断。
- 发布前首次远端 freshness 检查曾被 GitHub 瞬时拒绝；复测同一 ED25519 key `SHA256:H1xBwagKgdzgqc7nm+K7dwJExyRvC9y96GnAAUDH+KA` 已成功认证为 `YuSaZh`，`git ls-remote` 也成功读取远端 `main=288524a4...`。密钥和 SSH 配置有效，无需恢复、添加或切换认证；继续原定发布流程。

## 会话：2026-08-13

### GUI 项目源重定位批次
- **状态：** complete
- 已按实时 Goal 和用户最终指令恢复仓库通用规则与三份持久计划：本机固定使用 `py -3.12`，允许 Python 依赖安装与质量/构建/打包验证；需新增非 Python 环境的内容交给 GitHub Actions，GitHub 操作使用本机 SSH/`gh` 凭据且禁止浏览器登录。
- 本机完整 pytest 首轮收集发现新增 `tests/ui/test_project_relocation.py` 与既有 `tests/unit/test_project_relocation.py` 同名，pytest 将二者导入为同一顶层模块而中断；保留独立 UI 对话框覆盖并重命名为 `test_project_relocation_dialog.py` 后解决。
- 最终 Python 3.12 coverage 通过：排除两个明确依赖 Windows SMB/UNC 环境且由 CI 临时 share 覆盖的节点后，`320 passed, 2 deselected`，总覆盖率 `84.41%`，高于 80% 门槛。
- Ruff 全仓通过；Mypy strict 对 64 个源码文件通过。
- 首次隔离 `py -3.12 -m build` 因本机缺少 Hatchling 而长时间停在临时环境依赖准备，终止后按 `hatchling>=1.27,<2` 安装 Python 构建后端，并用 `--no-isolation` 成功生成 sdist/wheel；wheel 已核对包含中英文翻译资源。
- PyInstaller 6.22.0 / Python 3.12.10 已按 Windows workflow 的 onedir 参数成功打包；EXE 与双语资源存在，在清空 Python/虚拟环境变量、PATH 仅保留系统目录的条件下，打包 EXE `--smoke-test` 退出码为 0。
- 一个基于过时 fork 上下文的旧审计子任务两次把 `AGENTS.md` 和三份计划覆盖为已失效的零执行规则；主任务已用 `get_goal` 实时核验本地 Python 3.12 执行授权，并停止该子任务，四份文件随后按用户最终规则恢复。
- 最终静态审查发现源选择指纹判断与快照指纹刷新之间存在竞态窗口；共享重定位服务现比较两次文件指纹，选择应用期间发生变化即拒绝，避免把未经确认的新内容保存为可信基线。
- 已补源选择与指纹刷新竞态的测试源码，以及 Windows 夹具的精确 MPLS `mtime_ns` 契约；局部恢复/重定位矩阵 36 项通过。
- 共享恢复服务已导出并同时接入 CLI/GUI；CLI 删除重复准备逻辑，GUI 仅在完整恢复和原子项目写回成功后一次性提交工作区。
- 提交 `e404ede4b66a36318eec44f6405c5a4e3a9720e5` 已通过精确 SHA 的 CI run `31694449905`：source distribution、Ubuntu 和 Windows 三个 job 全部成功；双平台 Ruff/Mypy/Pytest 成功，Windows 临时 SMB share 创建、真实 UNC 测试和清理成功，Ubuntu 四态 UI 截图生成与矩阵校验成功。
- 远程 artifacts 均存在且未过期：Windows reports `9178747986`、Ubuntu reports `9178736523`、UI screenshots `9178736035`、source distribution `9178718181`。本机 `gh` 缓存 token 可读公开元数据但下载 ZIP 返回 401，因此本轮不能重复人工目视截图；截图步骤和矩阵门禁已由 Actions 成功执行，既有人工视觉基线仍为 run `31685081960`。
- 映射契约并行查询误引用了不存在的 `tests/unit/test_application_mapping.py`，命令仅完成部分只读输出且未修改文件；后续按实际模块路径拆分查询，不重复该路径假设。
- 工作模型已按用户最终指令更新：本机固定使用 `py -3.12`，允许安装缺失 Python 包并运行测试、Ruff、Mypy、构建和打包；非 Python 环境验证转交 GitHub Actions。
- 根目录 `AGENTS.md` 已更新为上述规则并受 Git 跟踪；此前零执行规则已失效。
- Git/GitHub 操作继续直接复用本机 SSH/Git Credential Manager 凭据，不通过浏览器登录、不替换身份、不修改全局 Git 配置；`gh` 缓存 token 与 Git SSH 凭据分别判断，下一次提交按精确 SHA 推送并审计远程结果。
- 已显式读取 `C:\Users\Hanam\.ssh\config` 与 `known_hosts` 完成本机凭据只读验证：GitHub 返回 `origin/main` 为 `8fd25a72032de0cdc8f72104ca5c0de848be835d`。普通沙箱 SSH 调用超时，改用本机用户 SSH 配置后成功；`gh auth status` 仅显示其独立缓存 token 已失效，不影响 SSH 推送。
- `ProjectRestoreApplicationService` 现在一次性扫描、加载字幕、恢复映射/策略并准备合并，CLI/GUI 均消费同一不可变结果；取消、源变化或任一阶段失败均不改变旧工作区或项目文件。
- 本地 Python 3.12 完成可用验证；Windows SMB/UNC、跨平台和最终候选检查由精确 SHA 的 GitHub Actions 完成。
- 当前远程绿色基线为 `e404ede4b66a36318eec44f6405c5a4e3a9720e5` / run `31694449905`。
- changed/missing BDMV 或字幕源会进入独立待恢复流程；全部源完成验证前不会扫描、修改旧工作区、绑定新项目或写入 BDMV。
- 实现必须复用 `ProjectSourceRelocationService` 和原子项目保存，并保持核心逻辑 Qt/Windows API 无关、时间线为整数 90 kHz tick、CLI/GUI 共用应用服务。
- 本地源码、测试和构建命令固定使用 Python 3.12；不在本机新增非 Python 环境。
- GUI 在 changed/missing 后先完成逐源恢复，CLI 保持非交互阻断；两端共享相同的源身份、播放列表和映射复现契约。
- index/MPLS 重定位后的源检查、领域解析和最终执行指向同一组已确认路径。
- 播放列表时长/fingerprint、全部保存映射、`ConflictPolicySnapshot` 和 Script Info 冲突接受入口均已恢复并通过双平台 CI。
- 工作模型固定为先建立 Qt 无关的项目扫描身份校验及测试契约，再接 GUI 待恢复状态机；CLI 复用共享规则但维持现有 changed/missing 非交互阻断，不新增 `relocate` 命令。
- GUI 使用手工目录/文件选择器，不接入任务书未要求的自动候选搜索；changed 默认拒绝且 Escape 等同拒绝，应用前复核指纹，完整恢复和原子项目写回成功后才提交新工作区关联。
- 远程测试矩阵已明确覆盖 unchanged、missing/exact/changed、多源取消、stem/时长/fingerprint、零偏移未锁定映射、四字段冲突策略、Script Info 开关和各失败阶段的两阶段提交不变量。
- 更新工作模型时，首轮并行只读检查因可选 memory 搜索无匹配返回非零而未保留其他输出；已改用逐项 settled 结果恢复现场，未修改业务文件，也未执行项目代码。
- 本轮首次状态核对时业务源码干净；规划更新后的复核发现 `project/relocation.py`、`ui/main_window.py` 和新文件 `ui/project_relocation.py` 正被另一条流程并发修改。它们不是本轮工作模型更新所写，已完整保留且未暂存、未回退、未提交；继续开发前必须先确认写入已稳定并整体审查其契约。
- 早期静态复核时，这些在研改动仅形成角色/路径校验和重定位对话框草稿；后续已补齐共享应用准备服务、完整策略/映射恢复与测试，并由 run `31694449905` 闭环。
- 应用层只读审计的首轮编排因 JavaScript 数组少一个闭合括号而在命令执行前失败；已修正脚本并成功读取真实模块，未运行任何项目代码。
- 续接 Goal 后的首轮组合静态搜索把 PowerShell 不支持的 `*.md` 目录参数传给 `rg`，导致只读编排返回非零；未修改文件或执行项目代码，后续改为显式目录/文件读取并保留各项结果。
- 最新静态审计确认在研接口与既有测试尚未同步：`test_open_project_source_checks_are_shown_without_modal_dialog` 仍调用已删除的 `_show_source_checks()`，若直接推送必然失败；恢复测试还缺新 `pending_project_snapshot` 与 scan 身份前置状态，必须连同两阶段恢复契约一起更新。
- 已对照任务书 20.2、AC-06 和 23 节禁忌项：当前共享模块只验证 scan 身份，CLI 私有准备与 GUI 提前修改状态仍违反共享应用服务/两阶段提交要求；本批将先建立完整 Qt 无关准备结果，再让 GUI 在成功后单次提交。

### 详情与输出摘要批次
- **状态：** complete
- 继续开发时已核对 `main` / `origin/main` 均为 `251424a`；除三份规划文件外无未提交改动。
- 本批将按任务书原文接入已有 Qt 无关展示模型，补齐播放列表结构、源字幕详情及预计事件/样式/警告摘要；本地不执行任何构建或测试。
- 已实现播放列表双击/右键结构详情、字幕双击/右键源详情和双语只读详情窗口；GUI 仅消费应用层展示投影，不重新解析源文件。
- `MergeReport` 新增向后兼容的 `output_style_count`，ASS 使用合并后真实样式数，SRT/SUP 为 0；预检摘要显示预计事件、样式和警告数量。
- 输出目标表已扩为完整路径、格式、编码、冲突策略和备份状态等 7 列；SUP 编码显示为二进制，路径列使用伸缩宽度，其余列保持可扫描。
- 字幕详情按表格路径定位重排后的资产，并纳入该文件对应的应用层 warning；已补合并报告、ASS、翻译、GUI 详情、输出摘要及远程截图断言。
- 播放列表详情补齐多角度、Mark 源字段和时间线指纹，并将已知推荐依据及 MPLS 诊断映射为双语展示；未知诊断保留原文，避免丢失信息。
- 本地静态检查确认编辑过的 Python 文件无超过 100 字符的行、双语 JSON 各 224 个键且集合/占位符一致、`git diff --check` 通过；等待提交并由 GitHub Actions 执行验证。
- 提交 `64e22a3` / run `31679107948` 已全绿：源码包、Ubuntu/Windows Ruff、Mypy、Pytest、真实 Windows UNC 和 Linux UI 截图矩阵全部通过。
- 下载并审计 artifacts `9172753453`、`9172741310`、`9172740974`：Ubuntu 261 项（2 skipped）、Windows 261 项，均为 0 failures / 0 errors；coverage XML 行覆盖率为 87.06%/87.04%。四张截图哈希互异，目视无重叠、截断或 CJK 缺字，新增完整输出摘要在中英文和高 DPI 画面中可见。

### 发布安全阻断项批次
- **状态：** complete
- 当前绿色基线 `64e22a3` 的 Windows Package run `31679478339` 已成功；远程完成 x64 onedir、许可证闭包、ZIP/SHA256、中文空格路径解压和无 Python EXE 烟测。
- 已静态审计 artifact `9172908967`：ZIP 为 57,029,081 字节、314 个条目且只有 `BDSubMerge/` 顶层；EXE、双语资源、项目/Qt/Python/安装依赖许可证及 manifest 全部存在，SHA256 与远程清单精确一致。
- 当前源码批次拒绝将目录、链接或其他非普通文件作为字幕输出目标，并在原子提交前再次防御预检后竞态，避免 `BACKUP/OVERWRITE` 移动目录。
- GUI 生成结果 `succeeded=False` 时现在保留失败终态和错误详情，不再显示“写入 0 个文件”或被 finished signal 覆盖为完成。
- 真实 BDMV 扫描与字幕加载捕获 size/mtime 指纹，prepare 与 execute 均复核 `index.bdmv`、MPLS 和字幕源；加载期间或预检后变化都会阻断写入。已补对应远程回归测试，本机未执行。
- 提交 `e5ae7b5` / run `31681278331` 已通过源码包、Ubuntu/Windows Ruff、Mypy、275 项 Pytest、真实 Windows UNC 和 Linux 四态截图矩阵；coverage XML 行覆盖率为 87.10%/87.09%，artifacts 为 Windows reports `9173588434`、Ubuntu reports `9173572981`、UI screenshots `9173572703`。
- 四张截图哈希与上一绿色批次一致，人工检查无重叠、截断、CJK 缺字或视觉回归。

### 预检 warning 明确确认批次
- **状态：** complete
- 任务书 18 节要求 error 禁止输出、warning 由用户确认后输出、info 无需确认；当前应用层 `PreparedMerge.ready` 已负责 error 门禁。
- GUI 仅在 ready 预检包含 warning 时显示双语确认框，默认按钮和 ESC 都是“否”；拒绝不启动后台写入，确认后才创建执行请求，无 warning 的正常流程不增加点击。
- 已补 warning 拒绝/确认、info 直接生成、error 不输出及确认框默认值/本地化的远程测试代码；本机不执行测试、lint、类型检查或构建。
- 提交 `615d955` / run `31682267166` 已全绿：源码包、Ubuntu/Windows Ruff、Mypy、Pytest、真实 Windows UNC 和 Linux 四态截图矩阵全部通过。
- JUnit artifact 显示 Ubuntu 280 项中 278 passed、2 skipped，Windows 280 passed，均为 0 failures / 0 errors；coverage XML 行覆盖率为 87.21%/87.19%，终端综合覆盖率为 83.47%/83.46%。
- 已审计 artifacts `9173966862`、`9173955837`、`9173955449`：四张 PNG 尺寸和 SHA256 与 Actions 日志一致、哈希互异，目视无重叠、截断、CJK 缺字或视觉回归。

### 共享应用服务 warning 门禁批次
- **状态：** complete
- 后续静态审计发现 `615d955` 只在 GUI 调用前确认，其他调用者仍可直接执行带 warning 的 `PreparedMerge`；CLI 还会默认接受低置信度，与任务书和共享应用服务边界不一致。
- 当前实现让 prepare 保留播放列表、字幕、映射、合并和输出 warning，`execute()` 在真实写入前统一要求 `accept_warnings=True`；dry-run 和 validate 保持无写入预览语义。
- GUI 仅在确认后传入接受标志；CLI 新增显式 `--accept-warnings`，并同步双语用户指南。已补共享服务、AC08、GUI 和 CLI 参数穿透的远程测试代码。
- 提交前静态审查已完成：全部执行调用点按真实 warning 来源核对，CLI 重复诊断已保序去重；14 个修改文件通过 `git diff --check`，所有修改 Python 文件均不超过 100 字符，等待精确提交的 Actions 验证。
- 提交 `cd64bcf` 已使用本机 SSH 凭据推送；run `31684849411` 的源码包通过，Ubuntu/Windows 均在 Ruff 报同一处未使用的 `dataclasses.replace` 后停止。已按 annotation 删除该导入，等待下一精确提交重新执行完整门禁。
- 修复提交 `8fd25a7` / run `31685081960` 已全绿：源码包、Ubuntu/Windows Ruff、Mypy、Pytest、真实 Windows UNC 和 Linux 四态截图矩阵全部成功。
- JUnit artifact 显示 Ubuntu 288 项中 286 passed、2 skipped，Windows 288 passed，均为 0 failures / 0 errors；coverage XML 行覆盖率为 87.54%/87.52%。
- 已审计 artifacts：Windows reports `9175097451`、Ubuntu reports `9175090247`、UI screenshots `9175089638`、source distribution `9175057242`。四张 PNG 分辨率和 SHA256 均有效且互异，目视无重叠、截断、CJK 缺字或视觉回归。

### M0-M4 基线
- **状态：** complete
- 已建立项目骨架、架构、CI、领域模型、BDMV 核心、文本字幕合并、自动映射和输出系统。
- 已推送至 `main`，当前远程提交为 `1287bf3`。

### M5 集成
- **状态：** complete
- 已接收三个并行开发结果：SUP/PGS、项目持久化、应用服务编排。
- 正在统一 `SubtitleAsset`、SUP 加载/合并和项目路径语义，并补齐集成测试。
- 已补齐应用服务的 SUP 类型导入，并新增基于 PCS 清屏信息的时长投影。
- GitHub CI 将在所有平台上传 JUnit/coverage 报告，并检查 wheel/Windows 包内的双语资源。
- Windows 打包工作流将以 offscreen 模式实际启动打包后的 GUI 并完成无交互烟测。
- 本地仅执行文件读取、文本搜索、`git diff --check` 等非构建检查。

### CLI、GUI 与 M6 验收
- **状态：** in_progress
- 工作模型已更新：本机固定使用 `py -3.12`，允许 Python 依赖安装、测试、Ruff、Mypy、构建和打包；需新增非 Python 环境的内容由 GitHub Actions 验证。
- Git/GitHub 操作继续调用本机现有凭据，不通过浏览器重新登录；当前仓库远端为 `git@github.com:YuSaZh/BDSubMerge.git`。
- 已在本机用户上下文验证 SSH 与 `gh` keyring：远程 `main` 为 `fdfddf9`，本地与
  `origin/main` 分歧为 `0/0`，`YuSaZh` 的现有 `gh` 凭据具备 `repo` 权限。当前无环境阻塞。
- 本机现有 Python 3.12.10，且 pytest、Ruff、Mypy、build、Hatchling、PyInstaller 与 PySide6 已安装；默认 Python 3.14 不用于本项目。
- CLI、双语 PySide6 工作区、项目打开/保存、用户边界、AC-01 至 AC-10 测试正在合并。
- 已为同刻用户/自动边界补充持久化锁 ID 规范化，避免项目恢复时锁引用失效。
- 已补齐真实 Shinya MPLS 契约、AC-01 至 AC-10 直接验收、五种 GUI 输出策略与
  自定义目录/模板控件。
- 当前 GUI 批次已实现字幕目录递归导入、自然排序与手动顺序恢复，逐集边界下拉、
  时间线双向选择与拖动锁定、陈旧预检隔离、映射重置、三种时间显示、区间冲突/
  超界/未映射展示，以及多输出目标和可选合并报告配置；已补对应 UI/单元测试，
  等待 GitHub Actions 验证。
- 远程 Windows CI 将建立临时 SMB 共享做真实 UNC 原子写入；Windows 打包将验证
  中文路径、无 Python PATH 启动、Shinya/pysubs2 导入及许可证材料。
- 下一步统一推送，由 GitHub Actions 验证 CLI/UI/acceptance 与无头截图。
- run `31630779273` 显示 source distribution 成功，Ubuntu/Windows 均在相同 16 项
  Ruff 诊断处停止；已逐项修复并以提交 `f8c0552` 推送。
- run `31659484298` 将 Ruff 诊断从 16 项缩小为 2 项确定性排序问题；修复后继续
  由远程验证 Mypy、Pytest、UNC 和 UI 截图。

## 远程测试结果
| GitHub run | 平台/任务 | 实际结果 | 状态 |
|------------|-----------|----------|------|
| 31624497128 | Source distribution | 构建成功 | pass |
| 31624497128 | Ubuntu Ruff/Mypy/Pytest | 64 项测试通过 | pass |
| 31624497128 | Windows | 安装依赖中 | running |
| 31624497128 | Windows 最终结果 | Ruff、Mypy、64 项测试通过 | pass |
| 31627068738 | Ubuntu、Windows、Source distribution | M5 核心全任务通过 | pass |
| 31630779273 | Source distribution | 构建及双语 wheel 资源检查成功 | pass |
| 31630779273 | Ubuntu、Windows | 相同 16 项 Ruff 诊断，后续步骤跳过 | fail |
| 31659484298 | Source distribution | 构建及双语 wheel 资源检查成功 | pass |
| 31659484298 | Ubuntu、Windows | Ruff 剩余 2 项排序诊断，后续步骤跳过 | fail |
| 31659898600 | Source distribution、Ubuntu/Windows Ruff | 构建和 Ruff 全部通过 | pass |
| 31659898600 | Ubuntu、Windows Mypy | 相同 6 项严格类型诊断，后续步骤跳过 | fail |
| 31660360425 | Source distribution、Ruff、Mypy、Windows SMB 建立 | 全部通过 | pass |
| 31660360425 | Ubuntu、Windows Pytest | 161 通过、2 失败、2 跳过；覆盖率 78.10% | fail |
| 31662574227 | Source distribution、Ubuntu/Windows Ruff | 全部通过 | pass |
| 31662574227 | Ubuntu、Windows Mypy | 运行日志路径局部变量类型冲突，4 项同源诊断 | fail |
| 31662716282 | 完整 CI | `bc79a73` 类型修复后全平台 CI 与真实 Windows UNC 验收通过 | pass |
| 31662921037 | Windows Package | onedir 构建与依赖许可证收集通过；Qt LGPL 文件名门禁误判，ZIP 前停止 | fail |
| 31663297253 | 完整 CI | `0ff9b9b` 的 Ubuntu/Windows、真实 UNC 与源码包全部通过 | pass |
| 31663324198 | Windows Package | wheel 元数据实际未提供 LGPL 正文；构建与依赖许可收集通过，ZIP 前停止 | fail |
| 31663851504 | 完整 CI | `97f3ba4` 的 Ubuntu/Windows、真实 UNC 与源码包全部通过 | pass |
| 31663862171 | Windows Package | 许可证、ZIP/SHA 均成功；GUI 子系统未设置 `$LASTEXITCODE` 被误判 | fail |
| 31664097386 | Windows Package | onedir、许可证、ZIP/SHA 与无 Python GUI 烟测全部通过 | pass |
| 31665015857 | 完整 CI | 协作取消链路在 Ubuntu/Windows、真实 UNC 与源码包全部通过 | pass |
| 31665235086 | 完整 CI | 重定位/展示模型源码包通过；Ubuntu/Windows 同在 Ruff 阶段失败，日志权限受限 | fail |
| 31665885218 | 完整 CI | `1ca58d6` 的 Ubuntu/Windows Ruff、Mypy、Pytest、真实 UNC 与源码包全部通过 | pass |
| 31667939630 | 完整 CI | `62b9e06` 源码包通过；Ubuntu/Windows 均仅在 `application.__all__` 的 RUF022 排序诊断处停止 | fail |
| 31668089029 | 完整 CI | `fdfddf9` 源码包及双平台 Ruff 通过；双平台 Mypy 同在 3 处类型收窄失败，Pytest 未运行 | fail |
| 31669097224 | 完整 CI | `bca41f6` 源码包、Ubuntu/Windows Ruff/Mypy/Pytest 与真实 UNC 全部通过 | pass |
| 31674632907 | 完整 CI | `04e4e32` 源码包成功；双平台 Ruff 同报 2 项，后续步骤跳过 | fail |
| 31674853072 | 完整 CI | `f5c1a38` 源码包、双平台 Ruff/Mypy、Windows SMB/UNC 通过；双平台同一 GUI 测试替身契约失败，截图跳过 | fail |
| 31675293315 | 完整 CI | `251424a` 源码包、双平台 Ruff/Mypy/Pytest、真实 Windows SMB/UNC、四态截图与 artifact 全部通过 | pass |
| 31678423407 | 完整 CI | `4cd77f7` 源码包成功；双平台 Ruff 同报 `test_details.py` 中文全角标点 RUF001，Mypy/Pytest/截图未运行 | fail |
| 31678761361 | 完整 CI | `8d4bfca` 源码包成功；双平台 Ruff 暴露余下 9 个中文全角标点 RUF001，后续阶段未运行 | fail |
| 31679107948 | 完整 CI | `64e22a3` 源码包、双平台 Ruff/Mypy/Pytest、真实 Windows UNC、四态 UI 截图与 artifact 全部通过 | pass |
| 31679478339 | Windows Package | `64e22a3` x64 onedir、许可证、ZIP/SHA256、中文空格路径无 Python EXE 烟测与 artifact 全部通过 | pass |
| 31681278331 | 完整 CI | `e5ae7b5` 源码包、双平台 Ruff/Mypy/Pytest、真实 Windows UNC、Linux 四态 UI 截图矩阵与 artifacts 全部通过 | pass |
| 31682267166 | 完整 CI | `615d955` 源码包、双平台 Ruff/Mypy、Ubuntu 278 passed / 2 skipped、Windows 280 passed、真实 UNC 与四态截图全部通过 | pass |
| 31684849411 | 完整 CI | `cd64bcf` 源码包成功；双平台 Ruff 同报一个未使用导入，后续步骤跳过 | fail |
| 31685081960 | 完整 CI | `8fd25a7` 源码包、双平台 Ruff/Mypy/Pytest、真实 Windows UNC、四态截图与 artifacts 全部通过 | pass |

## 错误日志
| 阶段 | 错误 | 解决方案 |
|------|------|---------|
| M1-M4 CI | Ruff、Mypy 分轮发现问题 | 逐次按远程日志修复，未在本机执行检查 |
| Shinya contract | 缺少剪辑标识时适配器静默使用默认值 | 改为强制字段并增加契约测试 |
| 静态搜索 | PowerShell 下向 `rg` 传递文件名通配符触发 Windows 路径错误 | 改用目录参数加 `--glob` 过滤 |
| 外部资料查询 | 搜索工具返回 HTTP 500 | 不重复请求；保留任务书语义，等待真实夹具契约测试 |
| Qt 许可旧链接 | 官方义务页面旧 URL 返回 404 | 改用 Qt for Python 官方 licenses 页面与有效源码目录 |
| Git push 超时 | 沙箱 OpenSSH 读取 `CodexSandboxOnline` 的 known_hosts | 显式使用 Hanam 本机 SSH config/known_hosts，提交 `f8c0552` 推送成功 |
| M6 严格类型 | 两个平台在 UI/CLI 发现相同 6 项 Mypy 错误 | 按真实模型字段和 Qt/argparse 状态显式收窄，继续远程验证 |
| AC-06 路径恢复 | 相对路径拼接保留词法 `..`，恢复状态与原状态不相等 | 对输入/输出恢复路径做不访问文件系统的词法规范化 |
| 运行日志路径类型 | Windows base 字符串与 Unix Path 复用同名变量导致 Mypy 冲突 | 拆分平台局部变量，提交 `bc79a73` 推送远程验证 |
| Package Qt 许可门禁 | PySide6 6.11.1 wheel 元数据未提供可验证的 LGPL 正文 | 从匹配的 PySide 源码标签逐字纳入 LGPLv3/GPLv3，固定 Git blob 并设为硬门禁 |
| 恢复状态并行查询 | 一个无匹配项使整组查询退出，未返回可用状态 | 拆分关键查询并对可选搜索独立处理 |
| 许可证脚本路径假设 | 假定存在独立 `scripts/collect_dependency_licenses.py` | 读取真实工作流，确认收集逻辑内嵌在 YAML |
| 映射模块路径假设 | 假定映射实现为 `src/bdsubmerge/mapping.py` | 用 `rg --files` 确认其为 `mapping/` 包，再按真实模块读取 |
| 文件规划记录补丁 | 将 `progress.md` 的预期行误用于 `findings.md` 上下文 | 按两份文件各自结构拆分补丁 |
| 许可证 Base64 转补丁 | 编排环境无 `atob`，随后低输出预算截断 Base64 | 改用 GitHub raw media type并提高单次读取预算，正文通过 `apply_patch` 写入 |
| Package GUI 退出码 | 直接调用 `--windowed` EXE 后 `$LASTEXITCODE` 为空，门禁误判 | 使用 `Start-Process -Wait -PassThru` 读取真实 `ExitCode` |
| Ruff 失败日志权限 | `gh run view --log-failed` 返回 403，check annotations 只有退出码 | 将 Ruff 输出设为 GitHub annotations，下一轮直接暴露文件、行号和规则 |
| GUI 批次导出排序 | run `31667939630` 两平台均报告 `application.__all__` 的 RUF022 | 将新增全大写常量导出归入现有常量分组后重新推送验证 |
| GUI 批次严格类型 | run `31668089029` 两平台共现 3 个根因 | 拆分 `boundary_id` 与两处 `mapping` 局部变量，并随精确 tick 批次推送验证 |
| 规划文件同步 | 首次补丁把错误表上下文放错文件，补丁整体未应用 | 按文件真实上下文拆分后重新应用 |
| GitHub 凭据上下文 | 沙箱内默认 `gh` 状态和 `known_hosts` 产生误判，提升权限后的首次命令又未继承仓库目录 | 使用本机用户凭据上下文，并以显式 `git -C`、SSH config/known_hosts 和远程 URL 验证；SSH 与 `gh` 均成功 |
| UI 截图步骤未执行 | CI 条件误用 `runner.os == 'Ubuntu'`，绿色 run 中截图步骤持续 skipped | 改为 `runner.os == 'Linux'`，当前批次推送后下载 artifact 审查 |
| PowerShell `rg` 路径通配符 | 将 `README*` 作为直接路径传给 `rg` 导致 Windows 路径错误，整组只读查询中断 | 改用 `--glob 'README*'`，没有重复错误命令 |
| 应用服务模块路径假设 | 假定存在 `application/merge.py`，只读查询因文件不存在而中断 | 先用 `rg --files` 定位真实的 `application/services.py` 与 `application/models.py` |
| UI 控件模块路径假设 | 假定存在 `ui/widgets.py`，只读查询因文件不存在而中断 | 改为先列出 `src/bdsubmerge/ui` 后读取真实控件模块 |
| 截图矩阵补丁上下文 | 将 `progress.md` 的预期行误放入截图脚本补丁段，补丁整体未应用 | 拆成 workflow、脚本和进度日志三个真实上下文后重新应用 |
| PowerShell `rg` 正则引号 | 双引号内的 `kind=\"preflight\"` 被 PowerShell 截断，导致正则未闭合 | 改用 PowerShell 单引号保护完整正则 |
| 本机凭据推送仓库所有权 | 提升到 Hanam 用户后，Git 发现 `.git` 由 Codex 沙箱账户创建并拒绝访问 | 不改全局配置；仅在本次 Git 命令使用 `-c safe.directory=D:/GitLibrary/BDSubMerge` |
| `gh release list` JSON 字段 | 当前本机 `gh` 不支持请求 `url` 字段，整组只读查询中断 | 使用命令列出的可用字段重新查询，不重复无效参数 |
| 原子写入模块路径假设 | 假定实现位于 `output/atomic.py`，只读查询因文件不存在中断 | 先用 `rg --files src/bdsubmerge/output` 定位真实模块后再审计 |
| 进度审计合并模块路径 | 假定 ASS/SRT/SUP 各有独立合并模块，三个只读读取失败 | `rg --files` 确认文本合并集中于 `merge/engine.py`，SUP 集中于 `subtitles/pgs_adapter.py` |
| 进度批次远程 Ruff | run `31674632907` 两平台同报 `SubtitleInput` F821 与 `os.path.abspath` PTH100 | 补应用模型导入，改用不解引用的 `Path.absolute()` 保留路径错误隔离语义 |
| 进度批次远程 Pytest | run `31674853072` 两平台同一 GUI 测试替身不接受新增 `cancellation_check` 关键字 | 同步两处 `load_ordered` 测试替身与应用服务接口，继续远程验证 |
| 详情翻译补丁上下文 | 翻译 JSON 的新增键并非文件末尾，首次组合补丁未匹配且未产生部分写入 | 按真实键位置拆分补丁并继续静态审查 |
| 详情批次缺失导入 | 预检摘要使用 `ApplicationSeverity`、输出摘要使用 `SubtitleFormat`，初稿未显式导入 | 提交前静态审查补齐两个导入，等待远程 Ruff/Mypy 验证 |
| 未跟踪文件差异误读 | 普通 `git diff` 不显示新建的 `details.py`，一度误判文件名字段位置 | 显式读取所有未跟踪文件，并在暂存后审查完整 cached diff |
| 详情补充字段语义 | 仅凭旧 formatter 变量名一度把指纹第四项标成连接条件，实际构造源 `equivalence.py` 使用 `selected_angle` | 按构造契约改为选中角度，并同步 Qt/非 Qt 格式化断言 |
| 详情批次远程 Ruff | run `31678423407` 双平台仅报新增中文断言的 10 个全角标点 RUF001 | 对精确 UI 预期字符串添加逐行 `noqa`，不改用户可见中文 |
| 详情批次远程 Ruff 续报 | run `31678761361` 显示首轮 annotations 未列全的 9 个同类诊断 | 静态扫描本批全部 Python 文件的全角括号、冒号和逗号，一次性补齐逐行豁免 |
| CI 流式监控超时 | `gh run watch` 的本地命令上限设为 1 秒，监控进程先于远程 run 完成被终止 | 改用 `gh run view` 短查询轮询精确 run ID，不将本地监控超时视为 CI 失败 |
| PowerShell `rg` 组合正则引号 | 双引号命令中的转义破坏字符组，导致正则未闭合且整组只读查询停止 | 后续拆分查询或使用 PowerShell 单引号保护正则，不重复失败命令 |
| `gh api -R` 版本兼容 | 当前本机 `gh api` 不支持仓库短参数，命令在请求前退出 | 改用包含 `repos/YuSaZh/BDSubMerge` 的完整 endpoint，annotations 读取成功 |
| warning 门禁远程 Ruff | run `31684849411` 双平台同报 AC-08 改写后遗留的未使用 `dataclasses.replace` | 删除唯一未使用导入，按新 SHA 重新触发完整 CI |

### UI 截图发布证据
- **状态：** complete
- Linux CI 显式安装 Noto CJK 字体，避免默认中文截图出现缺字或字体漂移。
- 截图改为精确 PNG 路径的独立 artifact，缺失即失败并保留 30 天；JUnit/coverage 也改为精确路径硬门禁。
- 截图场景通过共享应用服务生成完整映射、输出和报告预检；矩阵覆盖中英文、系统/浅色/深色及 150% 高 DPI，并要求四张图片哈希互异。
- run `31672669445` 的四张截图 step、矩阵校验与独立 artifact `9170299987` 全部成功；下载后 SHA256 与远程日志逐一一致。
- 人工审计中文浅色、英文深色、中文系统主题和英文 150% 高 DPI：字体正常、无重叠或截断，完整映射、输出路径、报告路径和预检就绪状态均可见。

### GUI 异步状态一致性批次
- **状态：** complete
- 已完成显式整行字幕重排、解锁清 offset、非法时间线拖动回滚和运行中预检 pending。
- 已冻结任务期间搜索、时间格式、offset、备注、高级开关与目录 drop，并修复任务失败终态和项目恢复 pending 泄漏。
- 已将当前 `.bdsm.json` 加入普通字幕输出保护路径，防止 full-path 目标覆盖项目文件。
- 对应 UI 回归已由 run `31672669445` 验证：Ubuntu 230 passed、2 skipped、82.93%；Windows 232 passed、82.92%，真实 SMB/UNC 验收通过。

### 工作模型更新
- **状态：** complete
- 当前 goal 已处于 active，目标是完成 BDSubMerge 1.0；仓库级 `AGENTS.md` 约束已作为后续工作的硬边界。
- 当前已验证代码基线为 `8fd25a72032de0cdc8f72104ca5c0de848be835d` / run `31685081960`；任何后续改动仍必须由自己的精确 SHA 重新通过 Actions，不能继承该绿灯。
- 本轮开始时前序源指纹、输出目标和 GUI 失败终态修复已完成提交与推送，源码工作树干净；仅本次工作模型记录产生规划文件变更。
- 后续执行模型固定为本地 Python 3.12 质量验证、`git diff --check`、提交、使用本机凭据推送、等待并审计同 SHA GitHub Actions；非 Python 环境只在远程配置。
- 发布候选必须在同一 SHA 上闭环 CI、Windows Package、ZIP/SHA256、许可证、版本一致性和最终 EXE 视觉证据，再创建 `v1.0.0` tag/Release。
- 本机凭据已实测可用：SSH 读取远程成功，`gh` keyring 的活动账号为 `YuSaZh`、Git 协议为 SSH 且具备 `repo` 权限；无需浏览器登录或补装本机开发环境。

### 共享 warning 门禁批次
- **状态：** complete
- 已恢复并静态审查 13 个未提交文件；共享应用服务、GUI 与 CLI 的显式确认穿透方向符合任务书严重度契约。
- 当前正在审查全部 `ExecuteMergeRequest` 调用及其真实预检 warning 来源，重点是 overwrite、auto-rename、SUP 估算时长和 AC-06 恢复后再次合并；本地未执行测试、lint、类型检查、构建或应用代码。
- 全部调用点静态审查完成：真实 warning 的成功写入均显式接受；AC-06 auto-rename 仅为 info，已补严重度断言，避免未来误放宽确认门禁。CLI 测试替身返回类型也已改为明确的 `tuple[CliIssue, ...]`。
- 静态审查发现共享 prepare 与 CLI preliminary 会重复汇总同一 playlist/subtitle warning；已在 CLI 最终结果边界按完整诊断保序去重，并补 validate 与 merge dry-run 回归。
- 14 个修改文件的静态检查已完成：`git diff --check` 通过，修改 Python 文件无超过 100 字符的行；按仓库约束未在本地运行代码，下一步提交并推送 GitHub Actions。
- run `31685081960` 已完成远程闭环：Ubuntu 288 项中 286 passed、2 skipped，Windows 288 passed；coverage XML 行覆盖率 87.54%/87.52%，真实 Windows UNC 与四态截图矩阵通过，人工截图审计无视觉回归。

### 实际任务进度批次
- **状态：** complete
- 已确认当前工作树将后台任务进度通过 `ContextVar` 从应用服务传到 Qt signal，并新增进度详情标签。
- 当前中间进度只覆盖字幕发现与逐文件加载；正在审计扫描、预检、事务合并等长任务及新增目录拖放/项目恢复分支，并补齐远程测试所需的静态测试代码。
- 已将字幕目录发现和字幕解析合并为同一个应用服务后台任务，增加逐路径取消检查、目录错误隔离和当前文件进度；失败或取消不会提交新的字幕工作区。
- 已修复项目打开的两阶段提交边界：新扫描成功后清除旧项目关联，仅在字幕完整恢复成功后绑定新项目文件；业务失败与线程失败都保持正确终态。
- 已补目录自然排序命名矩阵、取消、错误隔离、进度桥接、重复导入和项目恢复状态机的远程测试代码；本地未执行测试、lint、类型检查或构建。
- 已把当前文件进度扩展到 MPLS 扫描、预检、ASS/SRT/SUP 合并和多目标原子写入，并补框架无关的进度契约测试；实现完成，等待 GitHub Actions 验证。
- 提交 `f5c1a38` 的 run `31674853072` 已通过源码包、双平台 Ruff/Mypy 和 Windows SMB/UNC；唯一失败是 GUI 测试替身没有同步应用服务新增的取消参数，现已同时修正两处同类替身，等待下一轮远程验证。
- commit `251424a` / run `31675293315` 已完整通过：Ubuntu 254 passed、2 skipped，Windows 254 passed；coverage XML 行覆盖率 87.05%/87.03%，终端综合覆盖率 83.31%。Windows 临时 SMB 共享在测试前创建并在测试后清理。
- 已下载并审计 artifacts `9171310382`、`9171310713`、`9171325104`：四张中英文、明暗主题和 150% 高 DPI 截图哈希互异，目视无重叠、截断或 CJK 缺字；JUnit、coverage 与远程日志一致。

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | CLI/UI 与 M6 远程验收阶段 |
| 我要去哪里？ | Windows onedir 打包、artifact 审计与 1.0 发布 |
| 目标是什么？ | 交付 GitHub 远程验证通过的 BDSubMerge 1.0 |
| 我学到了什么？ | 见 findings.md |
| 我做了什么？ | 见上方记录 |

### 阶段 6 恢复与仓库规则核对（2026-08-13）
- **状态：** complete
- 本条记录的是当时采用、后来被用户明确撤销的旧规则：曾短暂禁止本机 Python 执行；当前规则已恢复为本机使用 `py -3.12` 完成 Python 依赖、测试、Ruff、Mypy、构建和打包。
- GitHub CLI 设备认证已由用户完成；本机 keyring 活动账号为 `YuSaZh`、Git 协议为 SSH 且权限完整，后续直接使用本机 `gh`/SSH 凭据，不再打开浏览器登录。
- 根目录 `AGENTS.md` 当时曾写入零执行限制；该限制现已撤销并改为允许本机 Python 3.12 验证，需要新增非 Python 环境的验证才交给 GitHub Actions。
- `v1.0.0` 发布提交为 `e42354dab36b3897f94da201259dc17b9550a02a`，annotated tag 已推送且解引用后精确指向该提交。
- 精确 SHA run `31694994062` 已全部成功：source distribution、Ubuntu/Windows Ruff/Mypy/Pytest、Windows 真实 UNC 建立与清理、Ubuntu 四态截图矩阵和 artifacts 上传均通过。
- 发布状态组合查询中的旧 `gh` API token 曾返回 401；用户随后通过 GitHub CLI 官方设备流程完成本机 keyring 登录。Hanam 本机用户上下文已验证完整申请 scopes、仓库 admin/maintain/push、Actions API 和 Release API，Git 协议仍为 SSH，当前 Release 列表为空。
- 已统一 `1.0.0` 版本元数据并更新双语 README、用户指南和 Changelog；Windows 工作流新增带版本号 ZIP、最终 EXE 版本校验和中英文包内截图 artifact。首轮 Ruff 通过，5 项局部测试全部通过但被全局 coverage 门槛判为命令失败；Mypy 唯一诊断为 Qt 图片格式参数类型，已针对性修正。
- 第二轮 Ruff 和 Mypy 均通过；局部测试暴露 PySide6 图片格式参数的类型桩/运行时差异，改由 `.png` 扩展名推断格式。工作流 YAML 静态解析还缺本地 `PyYAML`，将作为审计工具安装，不改变发布依赖。
- 完整本机测试收集 324 项，322 通过，coverage 84.66%；两项失败均为 AC-02 的 CI 专用 Windows SMB/UNC 条件，本机无临时共享。隔离 build 仅停在安装 Hatchling，改用已安装的 Hatchling 1.32.0 无隔离构建；远程仍需完整闭环这两条环境证据。
- 本机 PyInstaller 6.22.0 onedir 与无 Python `1.0.0` 烟测通过。首次 `offscreen` 最终 EXE 截图虽为 1440x1000 但中英文均缺字；原生 Windows 平台 A/B 截图字体正常，并发现英文界面 waiting 占位未刷新。已针对性修正工作流平台和占位翻译，等待重新验证。
- 最终本机闭环完成：323 passed、2 deselected、coverage 84.64%，Ruff/Mypy strict/YAML/diff 均通过；`bdsubmerge-1.0.0` sdist/wheel 的版本和双语资源已核对；PyInstaller 6.22.0 onedir、清空 Python 环境后的 `--expect-version 1.0.0` 烟测通过。
- 最终 EXE 原生 Windows 截图为中文浅色 `2160x1500` / SHA256 `90866d9ae73c17a5eeab63fd3c85533d12800828fcfa60565ad354a4093a71f3`，英文深色 `2160x1500` / SHA256 `eaa7225ad9bd7786d9c4b7848c37392b385434bea34f1af9cc5ba4fc1bca56e7`；人工审查字体、翻译、主题和布局正常，无重叠或截断。
- commit `5a5ed53` 的 CI run `31698531549` 已全绿；Package run `31698548909` 已通过版本、构建、许可证、ZIP/SHA256 和无 Python 烟测，但原生 Windows 截图在无交互 runner 挂起。已取消候选 Package run，改为离屏截图显式加载系统字体，等待新提交重新闭环。
- commit `e42354d` 的 CI run `31699687423` 已全绿：Ubuntu 323 passed、3 skipped、coverage 84.57%；Windows 326 passed、coverage 84.71%，双平台 Ruff/Mypy、Windows 真实 SMB/UNC 和 Ubuntu 截图矩阵均通过。
- 正式 tag push 的 Package/Release run `31702184769` 已全绿：版本/tag/x64、许可证、ZIP/SHA256、无 Python 启动、最终 EXE 中英文截图及公开 Release 创建均成功。
- `v1.0.0` Release 已发布且非 draft/prerelease；公开 ZIP 为 57,062,720 字节，SHA256 `89b690344ead539a8180fdc564192e5350d274438d47496dfe6977ede98d5093` 与清单一致。314 个条目无危险或重复路径，正式截图已人工确认无缺字、方框、重叠或截断。

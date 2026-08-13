# 发现与决策

## 需求
- v1.0.1 用户反馈包含七项：发布包不自动携带 `LICENSES/` 第三方许可证目录；README 列出参考开源项目并提供中文 README 链接；字幕区域增高且可拖动、列宽可调；错误/警告中文化；时间线滚轮缩放；报告未启用时折叠其选项；去除重复序号；边界表格仅显示章节而下拉选项显示章节与时间。
- 用户明确要求完成后发布 `v1.0.1`，Release notes 必须总结实际 Changelog，不能只有 `Full Changelog` 链接。
- 任务书 9.3 要求每个源字幕可查看文件名、格式、编码、事件数、样式数、最早开始、原始/有效结束、PlayRes、字体/图形附件、Aegisub Extradata 与警告数量；19.3 要求播放列表双击查看结构；19.5 要求输出区域显示完整路径、编码、冲突策略、备份、输出格式、预计事件/样式数量和警告摘要。
- 工具面向 Windows 11，输入 BDMV/PLAYLIST/MPLS/index.bdmv，输出外置 ASS/SSA/SRT/SUP。
- 任务书要求自动播放列表推荐、分集字幕映射、可视化时间线、多输出目标、项目复现和 CLI。
- UI 默认简体中文并支持英文，耗时任务必须在后台运行。
- 用户最新规则允许本机安装 Python 包并执行 Python 测试、Ruff、Mypy、构建和打包，所有本机 Python 命令固定使用 `py -3.12`。
- 当前仓库 `AGENTS.md` 和用户最新指令优先于旧 Goal、会话摘要或历史记录；只有需要新增非 Python 环境的验证才转交 GitHub Actions，最终推送提交仍按精确 SHA 审计。
- Git/GitHub 必须直接使用本机已有 SSH 与 `gh` 凭据；禁止转入浏览器登录或另建认证路径。
- 本轮实时验证确认 Hanam 本机 SSH 凭据已将 `YuSaZh/BDSubMerge` 远端 `main` 推送至 `e404ede4b66a36318eec44f6405c5a4e3a9720e5`；`gh` 的独立缓存 token 对 artifact 下载失效，不能据此误判 Git SSH 凭据不可用。

## 研究发现
- 2026-08-13 v1.0.1 发布前首次 SSH 连接曾返回 `Permission denied (publickey)`，但同一上下文复测立即成功：`ssh -T` 认证为 `YuSaZh`，`gh auth status` 显示活动账号和 SSH Git 协议，`git ls-remote` 读取远端 `main=288524a4...`。因此现有 key 与配置有效，首次拒绝属于瞬时认证失败，不能推断为 key 已从 GitHub 移除。
- 用户截图显示字幕表左侧 Qt vertical header 已显示 1/2/3，同时模型内“序号”列再次显示 1/2/3，属于重复信息；应保留一个序号来源。
- 用户截图显示字幕映射表默认只露出约两行，长字幕文件名被省略；应提高默认高度、使用可拖动 splitter，并保留列头拖动与完整文件名 tooltip。
- 用户截图显示“写入合并报告”未勾选时，报告格式、路径和冲突策略仍以 disabled 控件占据三行；应采用渐进披露，在关闭时隐藏整个报告配置容器。
- 字幕表当前将所有列设为 `ResizeToContents` 后又把文件名列设为 `Stretch`，会覆盖用户拖动后的宽度；改为可交互列宽，并只提供合理初始宽度和完整路径 tooltip。
- 时间线目前始终把完整播放列表时长映射到视口，没有可见范围状态；滚轮缩放应只改变 Qt UI 内的整数 tick 可见区间，并保持鼠标所在 tick 为缩放锚点。
- Windows 发布工作流当前显式复制 `THIRD_PARTY_NOTICES.md`、仓库 `licenses/*`，并从已安装分发中收集大量许可证到 `LICENSES/`；用户要求 v1.0.1 ZIP 仅保留本项目 `LICENSE`，因此需同步移除收集步骤与对应包内容门禁。
- 最新工作树已将 `ProjectRestoreApplicationService` 从应用包导出，并在 CLI `_prepare_project()` 与 GUI 后台项目恢复任务中调用；早期“尚未接入”的记录已过时。当前证据缺口转为完整服务级回归、UI 两阶段提交细节和旧 CLI 测试替身兼容性。
- 2026-08-13 用户最终纠正规则：本机可使用 `py -3.12` 安装 Python 包并执行测试、Ruff、Mypy、构建和打包；此前“全部交给 GitHub Actions”的描述已失效。
- `ProjectRestoreApplicationService` 已覆盖扫描身份、字幕加载、保存边界/映射锁、输出目标、冲突策略和映射复现检查，并成为 CLI/GUI 唯一恢复入口；GUI 从多回调状态变更改为成功后单次提交。
- 本机已有的 Python 3.12 项目工具可用于当前验证；不在本机新增非 Python 环境。
- `e404ede4b66a36318eec44f6405c5a4e3a9720e5` / run `31694449905` 已全绿：source distribution、Ubuntu/Windows Ruff/Mypy/Pytest、Windows SMB/UNC 生命周期和 Ubuntu 四态截图矩阵全部成功；四个 artifacts 存在且未过期。当前 `gh` token 下载 artifact ZIP 返回 401，因此本轮无法重复人工目视截图，不能把矩阵成功夸大为新一轮人工视觉审查。
- `e5abdf4cbd857d93c94c3df85c63b13ab66006eb` / run `31694994062` 也已全绿：source distribution、Ubuntu/Windows Ruff/Mypy/Pytest、Windows SMB/UNC 生命周期、Ubuntu 四态截图矩阵和 artifacts 上传全部成功，成为当前精确 SHA 绿色基线。
- 用户已通过 GitHub CLI 官方设备流程刷新 Hanam 本机 keyring 凭据；本机用户上下文中的 `gh` 现拥有完整申请 scope 集，对 `YuSaZh/BDSubMerge` 具有 admin/maintain/push 权限，Actions 与 Release API 均已验证可用。默认沙箱仍看见旧 token，因此后续 `gh` API 审计必须显式使用本机用户凭据上下文；Git 传输继续使用 SSH。
- `v1.0.0` 已从提交 `e42354dab36b3897f94da201259dc17b9550a02a` 正式发布。CI run `31699687423` 与 Package/Release run `31702184769` 全部成功；公开 ZIP SHA256 为 `89b690344ead539a8180fdc564192e5350d274438d47496dfe6977ede98d5093`。
- Windows runner 的原生 Qt 平台在无交互桌面时会挂起；最终 EXE 视觉证据改用 `offscreen`，并在截图入口显式注册系统中英文字体。PNG 细节、尺寸和哈希门禁仍由远程工作流验证。
- 当前最终源码本机验证为 323 passed、2 deselected、coverage 84.64%；两项 deselect 仅为要求 CI 临时 Windows SMB/UNC 环境的 AC-02。Ruff、Mypy strict、工作流 YAML、`git diff --check`、1.0.0 sdist/wheel、双语 wheel 资源、PyInstaller 6.22.0 onedir和无 Python EXE 版本烟测均通过。
- 正式公开 Release 非 draft、非 prerelease，包含版本化 ZIP 与 SHA256 清单。公开下载副本的 314 个归档条目无危险或重复路径，EXE、双语资源和许可证清单存在；正式中英文截图为 `1440x1000`，无缺字、方框、重叠或截断。
- GUI 项目源重定位缺口已关闭：打开项目遇到 changed/missing 输入时，在任何扫描或字幕加载前逐源定位；exact 直接接受，changed 默认拒绝并要求显式确认，完整成功后才原子写回项目。
- 项目恢复必须在任何 BDMV 重扫或字幕重载前完成源门禁；否则 GUI 会把重载后的当前指纹当作新基线，使项目保存时记录的 changed/missing 身份约束失效。全部源完成恢复前还必须禁止覆盖原项目文件和生成输出。
- `index_bdmv`、`playlist` 不能作为只改快照、不改实际读取源的孤立定位器。共享项目恢复服务必须构造并验证与已确认路径一致的运行时 layout/playlist/subtitles，CLI 与 GUI 都消费同一个准备结果。
- changed 候选的显式确认只授权接受内容变化，不授权跳过领域身份校验。index、MPLS 和字幕必须先验证角色、格式和播放列表身份；确认后刷新指纹并原子保存项目，下一次打开才应报告 unchanged。
- `ProjectSourceRelocationService` 已接入 GUI 手工目录/文件选择器；不接入任务书未要求的自动 `rglob` 搜索。
- `open_project()` 同时保留 `ProjectSnapshot` 与 `RestoredProject`，changed/missing 门禁先于扫描和加载，失败不会刷新错误基线。
- GUI 只有在完整恢复成功后才绑定 `project_path`；项目原子写回失败时保留旧工作区与旧项目文件。
- GUI/CLI 均校验保存的播放列表 stem、时长和 `timeline_fingerprint`。
- 保存映射的复现门禁必须覆盖全部映射，包括 `locked=False, offset=0`；仅恢复显式锁会让零偏移映射被重新求解，违反 AC-06。准备结果还必须逐项核对数量、顺序、路径、边界、offset 和 lock 状态。
- GUI 已恢复 `ConflictPolicySnapshot` 并投影 `MergeOptions`；`preserve_unknown_sections` 等项目策略在保存/恢复间透明往返。
- Script Info/PlayRes 冲突接受入口应位于折叠高级选项，默认关闭、双语可见；切换后必须让既有预检失效，并随项目保存/恢复。它是显式风险接受，不得静默放宽 warning 门禁。
- GUI 不接入同步 `rglob()` 候选搜索；每次手工选择应用时由共享服务重新计算并校验指纹，避免选择与应用之间的文件竞态。
- 本批不扩大 CLI 命令面：任务书最小命令清单不要求 `relocate` 子命令，现有 CLI 对 changed/missing 非交互阻断可保留；应共享的是准备服务及身份/映射/策略契约。
- 核心回归矩阵包括 unchanged 直接恢复、missing 在扫描前进入重定位、exact 文件免确认、changed 默认 No/ESC No、多源逐项恢复、播放列表 stem/时长/fingerprint 失败、零偏移未锁定映射复现、冲突策略四字段往返，以及扫描/字幕/原子保存失败的两阶段关联不变量。
- `docs/architecture.md` 明确规定 `project` 层只拥有版本化快照和中立状态 DTO，应用服务协调 BDMV、字幕、映射、预检和事务写入，GUI/CLI 不得复制规则；当前实现已把扫描身份校验和项目准备逻辑收敛到 `application` 层。
- 任务书 20.2 只明确要求文件缺失时允许用户重定位；21 节同时要求 CLI 无交互且 GUI/CLI 使用相同应用服务。这进一步支持“GUI 提供交互、CLI 保持阻断、两端共享无 UI 的恢复准备契约”。
- 任务书原文复核确认 AC-06 要求重新打开后映射、输出目标和未变化输入的输出内容保持确定，输入变化必须明确警告；20.2 还要求缺失文件可由用户重新定位。当前完整共享准备逻辑已位于 `application/project_restore.py`，CLI 私有 `_prepare_project()` 只作服务适配。
- GUI 已改为后台应用服务返回完整且已验证的准备结果，成功后才一次性投影状态；取消或中途失败保持旧工作区原样。
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
- 当前 goal 已处于 active；执行边界以仓库级 `AGENTS.md` 为准，本机执行 Python 3.12 验证，需要新增非 Python 环境的检查及最终精确 SHA 审计由 GitHub Actions 完成。
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
- 项目恢复准备若没有生成 mapping，必须同时返回合并服务的底层 error（如 `mapping_failed`）与恢复层的 `mapping_reproduction_failed`；只传播 `source_*` 会丢失可操作根因。

## 技术决策
| 决策 | 理由 |
|------|------|
| 项目拥有 ASS/SRT/PGS 解析与序列化模型 | 避免第三方内部模型泄漏到领域层 |
| Shinya 通过单一适配器隔离 | 第三方字段变化只影响边界层 |
| 映射使用确定性有序非重叠动态规划 | 同一输入应得到稳定、可解释结果 |
| 项目文件保存相对路径并保留绝对恢复提示 | 兼顾可迁移性和源文件重定位 |
| 项目恢复集中到共享应用服务 | 确保 GUI/CLI 对同一组确认路径、时间线身份、保存映射和冲突策略执行同一门禁 |
| CLI 不新增 `relocate` 子命令 | 任务书未要求该命令，现有非交互阻断已满足 CLI 边界，避免扩大发布表面 |
| CI 覆盖 Ubuntu 与 Windows | Linux 快速发现问题，Windows 验证目标平台 |

## 2026-08-14 发布后反馈定位
- 映射置信度不是单看可见时长差：`_interval_cost` 还计入边界置信度、短区间、估算时长，字幕超过区间时按 8 倍惩罚；`classify_confidence` 当前还会让 3% 范围内的局部替代候选无条件触发 low。
- 对截图中 23:39.930 与 23:39.960 的 30 ms 差值，纯时长成本远低于 medium/low 阈值；若显示 low，最可能是章节密集造成局部候选歧义，或边界置信度额外扣分。需要让歧义只降低本来就不够精确的候选，并在 UI tooltip 暴露评分/原因。
- 合并引擎只在 offset 后 `end <= 0` 时产生 `event_dropped_before_zero`；`start < 0 < end` 会裁剪并产生 `event_start_clipped`。因此大量 dropped 警告是大量事件整体落在零点前，不是 30 ms 尾差直接造成。
- 应用层给合并 notice code 加 `merge_` 前缀，中文资源键没有该前缀；UI 本地化应先尝试完整码，再安全剥离已知阶段前缀，稳定码与原始英文详情继续保留。
- ASS 分析的有效时长已忽略 `Comment` 尾部，但合并仍保留并时间平移全部事件。`offset=0 ms` 且起始边界为 `chapter:0` 时大量 `event_dropped_before_zero` 通常来自源 ASS 中结束时间为零的 Comment/模板/无效事件；它们会被逐条丢弃，UI 应合并重复提示，报告继续保留精确 dropped count。

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
# v1.0.2-beta.1 发布发现（2026-08-14）

- Python 包版本必须符合 PEP 440，因此 beta 版本写作 `1.0.2b1`；公开 Git 标签采用 SemVer
  `v1.0.2-beta.1`。打包工作流必须映射两者，不能直接用字符串相等判断。
- EXE `--expect-version` 应校验内部版本 `1.0.2b1`，ZIP 文件名和 GitHub Release 标题则应使用
  `1.0.2-beta.1`，避免用户面对 Python 版本拼法。
- 现有 Release 创建逻辑会把含连字符的 tag 标记为 prerelease，可直接覆盖本测试版语义。
# v1.0.2-beta.2 发行发现（2026-08-14）

- 用户实际运行窗口证明 `resizeColumnToContents` 只进行一次内容测量仍会让字幕名被省略；输出目标表
  的路径列虽然为 Stretch，也会被其他 `ResizeToContents` 列挤压。需要完整内容定宽配合水平滚动。
- Linux CI 既有 UI 截图只使用 `offscreen` 插件，不能代表公开 GUI 包可在 X11 启动；首个 Linux
  发行包必须通过 PyInstaller 原生构建以及 Xvfb 下的 `xcb` 启动和截图门禁。
- Linux onedir 使用 tar.gz 保留可执行权限；ZIP 不适合作为首个 Linux 原生发行格式。

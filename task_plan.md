# BDSubMerge 开发计划

## 目标
已按照项目任务书完成并发布 BDSubMerge 1.0；当前使用本机 Python 3.12 完成 Python 依赖、测试、质量检查、构建与打包，需要新增非 Python 环境的验证由精确提交 SHA 的 GitHub Actions 完成。

## 当前阶段
阶段 9/9 发布 `v1.0.2-beta.1` 测试版

## 工作模型（2026-08-13 用户最新确认）
1. `v1.0.0` 发布基线为提交 `e42354dab36b3897f94da201259dc17b9550a02a`；CI run `31699687423` 与正式 Package/Release run `31702184769` 均成功。
2. 当前仓库 `AGENTS.md` 和用户最新指令是执行边界的唯一准则；旧摘要、历史会话记录或工具建议不得覆盖这些规则。
3. 本机 Python 命令固定使用 `py -3.12`；允许安装 Python 包并执行测试、Ruff、Mypy、构建和打包。
4. 需要新增非 Python 环境的验证交给 GitHub Actions；最终推送提交仍须按精确 SHA 完成远程审计，包括双平台、Windows SMB/UNC 和发布候选验证。
5. 每个可审查批次都按“源码与测试编辑 -> 本机 Python 3.12 验证 -> `git diff --check` -> 提交 -> 使用本机 SSH/`gh` 凭据推送 -> 等待精确提交 SHA 的 GitHub Actions -> 审计日志与 artifact”闭环。
6. Git 操作直接使用本机现有 SSH/Git Credential Manager 凭据；不打开浏览器登录、不创建替代身份、不改全局 Git 配置。`gh` 缓存 token 与 Git SSH 凭据分开判断，Git 凭据可用时不得转入浏览器。
7. 遇到工作树来源、Git SSH 凭据、CI、artifact 或发布门禁异常时先停止扩大范围，保留现场并向用户确认；`gh` API 调用使用已刷新凭据的 Hanam 本机用户上下文，默认沙箱旧 token 不作为认证结论。
8. 发布顺序固定为：完成 GUI 项目源重定位 -> 复核剩余规范缺口 -> 收紧 Windows 包与版本/截图门禁 -> 统一 `1.0.0` 元数据和双语文档 -> 推送最终候选并审计 CI/ZIP/SHA256/许可证/视觉证据 -> 创建 `v1.0.0` tag 和 GitHub Release。
9. 项目恢复的身份规则由 GUI/CLI 共用的 Qt 无关应用代码负责；两端必须从同一组已确认路径完成源检查和时间线身份校验，禁止 GUI 复制 CLI 私有规则。
10. GUI 打开项目采用两阶段提交：全部 changed/missing 源恢复、验证和加载成功前，不扫描、不替换旧工作区、不绑定新项目、不覆盖项目文件、不生成输出；取消或失败保持旧工作区与原项目不变。
11. changed 文件默认拒绝，Escape 等同拒绝；应用时重新校验指纹。只有完整恢复成功后才原子写回重定位快照，否则旧工作区和项目关联保持不变。
12. CLI 维持现有 changed/missing 非交互阻断，不为本批新增任务书未要求的 `relocate` 命令；共享服务仍需让 CLI 与 GUI 的项目身份、映射和冲突策略门禁一致。

## 各阶段

### 阶段 1：M0 项目骨架
- [x] 项目元数据、许可证、双语 README
- [x] 架构文档与时间基准 ADR
- [x] GitHub CI 与 Windows 打包工作流
- **状态：** complete

### 阶段 2：M1 BDMV 解析核心
- [x] BDMV 发现、MPLS 适配与 90 kHz 时间线
- [x] 等价时间线分组与可解释播放列表排序
- [x] 单元与契约测试
- **状态：** complete

### 阶段 3：M2-M4 文本字幕、映射与输出
- [x] ASS/SSA/SRT 解析、合并、报告与 Golden Test
- [x] 确定性自动映射、边界、锁定与置信度
- [x] 输出目标、全量预检和原子写入
- [x] GitHub Ubuntu 验证通过（64 项测试）
- **状态：** complete

### 阶段 4：M5 SUP、项目持久化与应用编排
- [x] SUP/PGS 二进制解析、平移与追加
- [x] 版本化项目快照、路径恢复与迁移
- [x] 应用服务层和 dry-run 编排
- [x] 完成模块集成和静态检查
- [x] 推送并修复 GitHub CI 发现的问题
- **状态：** complete

### 阶段 5：CLI 与图形界面
- [x] 完成 scan、inspect、plan、validate、merge CLI
- [x] 完成简体中文/英文 PySide6 单窗口工作区
- [x] 后台任务、时间线、映射表、预检与项目开关
- [x] GitHub Actions 上通过 Ubuntu/Windows Ruff 与 Mypy
- [x] 修复项目相对路径恢复并让完整 Pytest/coverage 通过
- [x] 完成字幕目录导入、自然排序、调整顺序与项目恢复
- [x] 完成逐集手工映射、吸附、重置与无字幕区间控制
- [x] 补齐时间线的分集/未映射/冲突/选择状态和三种时间格式
- [x] 补齐多目标输出交互
- [x] 接入播放列表结构、源字幕详情和事件/样式/警告输出摘要
- [x] 修复精确 90 kHz offset、编辑/异步预检一致性与任务冻结缺口
- [x] 让取消信号贯穿长任务和事务写入
- [x] 显示实际进度详情（扫描、字幕、预检、合并和写入）
- [x] 使用 GitHub Actions 执行完整 CLI/UI 测试并人工审计截图
- [x] 建立 Qt 无关的共享项目扫描身份校验
- [x] 打开项目时为 changed/missing 输入提供逐源定位、取消和显式确认的 GUI 重定位流程
- [x] 恢复并校验播放列表时长、timeline fingerprint、全部保存映射和冲突策略
- [x] 增加默认关闭的 Script Info/PlayRes 冲突接受选项并保持未知段设置往返
- [x] 由精确提交的 GitHub Actions 验证双平台、UNC、取消、项目关联不变量和 UI 截图
- **状态：** complete

### 阶段 6：M6 打包、验收与发布
- [x] AC-02 覆盖真实 Windows SMB 上的扫描、预检和原子写入
- [x] AC-06 覆盖保存、关闭重开、再次合并和输出字节一致性
- [x] AC-09 覆盖运行中协作取消且取消生成不留下输出
- [x] 补齐 AC-01 至 AC-10 的具名验收和关键映射、ASS/附件/编码/路径测试矩阵
- [x] 实现用户应用数据目录运行日志和可选 JSON/文本合并报告
- [x] 在 `0.1.0.dev0` 基线上验证 Windows onedir ZIP、SHA256、许可证闭包和无 Python 启动链
- [x] 按错误/警告/信息严重度执行共享生成门禁，GUI/CLI 均需明确确认 warning
- [x] 在统一 `1.0.0` 后对同一最终候选重新执行 Windows 包、版本和视觉审计
- [x] 生成稳定 ZIP、SHA256，并完成 tag/Release 自动发布链
- [x] 完善双语 README、用户文档、报告、限制与本地测试证据
- [x] 完成统一 `1.0.0` 版本元数据的远程发布验证
- **状态：** complete

### 阶段 7：v1.0.1 用户反馈修复与发布
- [x] 精简发布包许可证内容，README 双语列明参考项目并提供中文 README 跳转
- [x] 字幕映射区域默认高度翻倍并支持手动拖动调整，列宽可调且长文件名可查看全文
- [x] 去除字幕序号的重复显示
- [x] 为错误和警告提供简体中文显示文本
- [x] 时间线支持鼠标滚轮缩放并保留可发现的缩放状态
- [x] 未勾选写入合并报告时折叠报告选项
- [x] 边界单元格仅显示章节，下拉选项保留章节与时间
- [x] 统一版本为 `1.0.1`，补充有实际内容的 Changelog 与 GitHub Release notes
- [x] 由精确 SHA 的 GitHub Actions 完成双平台测试、截图、Windows 打包和公开 Release 审计
- **状态：** complete

### 阶段 8：v1.0.1 发布后反馈修复（不发版）
- [x] 表格在可用宽度足够时完整显示内容，并继续允许手动调列宽
- [x] 边界下拉弹出列表独立加宽，收起值仍只显示章节 ID
- [x] 时间线滚轮缩放保持字体字形和字号不变
- [x] `merge_event_dropped_before_zero` 等带阶段前缀诊断正确中文化
- [x] 调整并解释近似精确映射被候选歧义过度降级的问题
- [x] 补齐局部与全量 Python 3.12 回归验证，不改版本、不打 tag、不发版
- **状态：** complete

### 阶段 9：v1.0.2-beta.1 测试版发布
- [x] 将 Python 包版本更新为 PEP 440 `1.0.2b1`，并映射到 SemVer 标签 `v1.0.2-beta.1`
- [x] 补充双语 README、Changelog 和包含实际改动摘要的 Release notes
- [x] 完成本机 Python 3.12 测试、Ruff、Mypy、构建与 Windows 包审计
- [ ] 提交并推送 `main`，按精确提交 SHA 审计 GitHub Actions
- [ ] 创建并推送 annotated tag，验证 prerelease、ZIP、SHA256 和许可证结构
- **状态：** in_progress

## 关键约束
1. 本机 Python 命令固定使用 `py -3.12`，允许安装 Python 包并执行测试、Ruff、Mypy、构建和打包。
2. 需要新增非 Python 环境的验证交给 GitHub Actions；最终提交必须通过精确 SHA 的远程 CI 审计。
3. Git 和 GitHub 操作使用本机现有凭据，不通过浏览器重新登录。
4. 遇到异常先定位根因；不得扩大系统或仓库变更范围。

## 已做决策
| 决策 | 理由 |
|------|------|
| 内部时间统一为整数 90 kHz tick | 避免浮点误差并与 PGS PTS 直接对应 |
| 领域、应用、UI、输出分层 | 保证 GUI/CLI 不承载核心合并规则 |
| 输出必须全量预检后原子写入 | 防止部分写入和原盘损坏 |
| SUP 仅平移 packet 时间戳 | 不做 OCR、渲染或重编码，保持 payload 不变 |
| CI 绿灯不是任务书完成的充分证据 | 必须按 AC、UI 细则、日志报告和发布产物逐项审计 |
| 不降低 80% 覆盖率门槛 | 用任务书要求的真实行为测试补足覆盖，而不是弱化门禁 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| 初始 CI Ruff 失败 | 1 | 按远程日志修复风格问题后重新推送 |
| 后续 CI Mypy 失败 | 1 | 修复严格类型推断后重新推送 |
| Shinya 缺少必填 ClipInformationFileName 未被拒绝 | 1 | 收紧适配器必填文本字段契约 |
| M5 远程 CI 验证 | 3 | 依次修复 Ruff 与 Mypy 后，run 31627068738 全平台通过 |
| M6 集成 Ruff | 2 | run 31630779273 的 16 项降至 run 31659484298 的 2 项并全部修复 |
| M6 集成 Mypy | 1 | run 31659898600 的 6 项严格类型错误已修复，run 31660360425 通过 |
| M6 集成 Pytest | 1 | run 31660360425 为 161 passed、2 failed、2 skipped；正在修复路径恢复并补真实验收覆盖 |
| 项目模型路径假设 | 1 | `project/models.py` 不存在；改用 `rg --files src/bdsubmerge/project` 定位真实模块 |
| 规划补丁上下文假设 | 1 | 按三份规划文件的真实结构分别更新，不复用错误表上下文 |
| GUI 批次严格类型 | 1 | run `31668089029` 的 3 个根因纳入当前修复批次 |
| CI 截图平台条件 | 1 | `runner.os` 实际为 `Linux`，修复误写的 `Ubuntu` 条件并等待远程截图审查 |
| GitHub 凭据上下文 | 2 | 不采用沙箱默认身份；显式使用本机用户 SSH 配置，并以用户 keyring 验证 `gh` |
| 工作模型补丁上下文 | 1 | 组合补丁引用了错误文件中的诊断行，且未产生部分写入；按三个规划文件的真实锚点拆分应用 |
| 本机凭据只读复核 | 2 | 沙箱不能读取用户 SSH 配置，外部 Git 又触发仓库所有权保护；改用完整远程地址、单次 `safe.directory` 和显式用户 SSH 配置，不改全局 Git |
| warning 批次组合补丁 | 1 | `findings.md` 的精确文本上下文不匹配，补丁整体未应用；拆分源码测试与规划记录后分别应用 |
| 工作模型组合补丁 | 1 | `progress.md` 的实际标题为“进度日志”，组合补丁整体未应用；按三个文件的真实锚点拆分更新 |
| 工作模型并行只读检查 | 1 | 可选的 memory 搜索无匹配返回非零，使首轮并行编排未保留其他输出；改用 `Promise.allSettled` 逐项保留结果，不重复失败方式 |
| 应用层只读编排脚本 | 1 | JavaScript 数组缺少闭合括号，命令在解析前即被拒绝；修正结构后成功读取，未执行项目代码或修改工作树 |
| Windows `rg` 通配符参数 | 1 | `rg ... src tests docs *.md` 在 PowerShell 下把 `*.md` 作为非法路径；改用显式文件或目录参数并逐项保留结果 |
| 映射测试模块路径假设 | 1 | 查询了不存在的 `tests/unit/test_application_mapping.py`，导致并行只读编排提前停止；改为按 `rg --files` 已确认的 mapping 模块和现有测试查询，并独立保留结果 |
| 发布状态组合查询 | 1 | `gh release list` 的独立 API token 返回 401，使同组只读输出未保留；不转入浏览器登录，改为拆分本地版本审计，并在最终发布前单独确认 `gh` API 权限 |
| 发布文档组合补丁 | 1 | README 中一条换行上下文与预期不完全一致，组合补丁整体未应用；拆分工作流与各文档补丁并按真实段落更新 |
| 局部版本测试 coverage | 1 | 5 项局部测试全部通过，但全局 80% coverage 门槛使单文件命令退出 1；局部回归改用 `--no-cov`，完整测试仍保留 coverage 门禁 |
| 发布截图 Qt 类型 | 1 | Mypy 要求 `QImage.save` 的格式参数为 bytes-like；将 `"PNG"` 改为 `b"PNG"` 后重跑严格类型检查 |
| 发布截图 Qt 运行契约 | 1 | PySide6 6.11.1 类型桩接受 bytes 格式名但运行时拒绝 `b"PNG"`；省略格式参数并由 `.png` 扩展名确定编码，同时满足运行时和 Mypy |
| 工作流 YAML 本地解析依赖 | 1 | 本机 Python 3.12 缺少 `PyYAML`；按仓库规则安装为本地审计工具，不加入项目运行依赖 |
| 完整测试本机 UNC 环境 | 1 | 324 项中 322 通过，2 项 AC-02 需要 CI 临时 SMB/UNC 环境；本机精确 deselect 两项，远程 Windows 必须完整执行并清理真实共享 |
| PEP 517 隔离构建下载 | 1 | `python -m build` 在隔离环境安装 Hatchling 超时；使用本机已验证的 Hatchling 1.32.0 执行 `--no-isolation`，远程 CI 仍保留隔离构建 |
| Windows 包截图缺字 | 1 | 最终 EXE 在 Qt `offscreen` 后端下中英文均渲染为方框；A/B 证明原生 `windows` 后端字体正常，工作流截图固定使用原生平台并保留隐藏自动捕获 |
| 英文 waiting 占位未刷新 | 1 | 语言切换只在摘要为空时填文案，初始化中文占位因此残留；仅当摘要仍是旧 waiting 占位时翻译，真实预检内容保持不变 |
| Windows 截图平台补丁上下文 | 1 | 首次环境补丁命中了烟测步骤而非截图步骤；提交前完整 diff 发现并纠正为烟测 `offscreen`、截图 `windows`，同时增加 PNG 细节大小门禁 |
| GitHub runner 原生截图挂起 | 1 | Package run `31698548909` 在原生 `windows` 截图步骤持续挂起；取消该 run，恢复 CI `offscreen` 并在截图专用入口显式注册 Windows 系统中英文字体，避免交互桌面依赖 |
| 进度审计模块路径假设 | 1 | ASS/SRT 实际统一位于 `merge/engine.py`，SUP 位于 `subtitles/pgs_adapter.py`；按 `rg --files` 的真实路径继续 |
| 进度批次远程 Pytest | 1 | run `31674853072` 两平台同一 GUI 测试替身不接受新增 `cancellation_check` 关键字；同步两处替身与应用服务接口后继续远程验证 |
| 默认沙箱 SSH 只读检查超时 | 1 | 显式读取 Hanam 本机 SSH config/known_hosts 后成功，确认远端 `main` 为 `8fd25a7`；不使用浏览器或失效的 `gh` token |
| 本地 ZIP 内容检查竞态 | 1 | 压缩与检查并行导致检查先于 ZIP 生成完成；压缩已成功，后续改为串行审计现有 ZIP |
| UI 截图参数假设 | 1 | `capture_workspace.py` 的目标路径是位置参数，不支持 `--output`；按脚本帮助更正调用 |
| GitHub SSH 瞬时拒绝 | 1 | 首次 publickey 失败后按边界停止；同一 key 复测认证为 `YuSaZh` 且 `git ls-remote` 成功，确认无需改 key 或认证配置并继续发布 |
| 发布后批次完整测试 deselect 路径过时 | 1 | collect-only 确认当前两项 AC-02 UNC 节点位于 `test_output_project_acceptance.py`，按精确节点重跑；不把环境失败归因于本轮源码 |

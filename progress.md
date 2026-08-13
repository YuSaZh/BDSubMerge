# 进度日志

## 会话：2026-08-13

### 详情与输出摘要批次
- **状态：** in_progress
- 继续开发时已核对 `main` / `origin/main` 均为 `251424a`；除三份规划文件外无未提交改动。
- 本批将按任务书原文接入已有 Qt 无关展示模型，补齐播放列表结构、源字幕详情及预计事件/样式/警告摘要；本地不执行任何构建或测试。
- 已实现播放列表双击/右键结构详情、字幕双击/右键源详情和双语只读详情窗口；GUI 仅消费应用层展示投影，不重新解析源文件。
- `MergeReport` 新增向后兼容的 `output_style_count`，ASS 使用合并后真实样式数，SRT/SUP 为 0；预检摘要显示预计事件、样式和警告数量。
- 输出目标表已扩为完整路径、格式、编码、冲突策略和备份状态等 7 列；SUP 编码显示为二进制，路径列使用伸缩宽度，其余列保持可扫描。
- 字幕详情按表格路径定位重排后的资产，并纳入该文件对应的应用层 warning；已补合并报告、ASS、翻译、GUI 详情、输出摘要及远程截图断言。
- 播放列表详情补齐多角度、Mark 源字段和时间线指纹，并将已知推荐依据及 MPLS 诊断映射为双语展示；未知诊断保留原文，避免丢失信息。
- 本地静态检查确认编辑过的 Python 文件无超过 100 字符的行、双语 JSON 各 224 个键且集合/占位符一致、`git diff --check` 通过；等待提交并由 GitHub Actions 执行验证。

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
- 工作模型已更新：本机禁止构建、测试、lint、类型检查、依赖安装和打包；仅允许源码检查、静态搜索、Git 操作与 `git diff --check`，所有执行型验证只走 GitHub Actions。
- Git/GitHub 操作继续调用本机现有凭据，不通过浏览器重新登录；当前仓库远端为 `git@github.com:YuSaZh/BDSubMerge.git`。
- 已在本机用户上下文验证 SSH 与 `gh` keyring：远程 `main` 为 `fdfddf9`，本地与
  `origin/main` 分歧为 `0/0`，`YuSaZh` 的现有 `gh` 凭据具备 `repo` 权限。当前无环境阻塞。
- 本机只有 Python 3.14.7，缺少项目要求的 Python 3.12 以及 pytest、Ruff、Mypy、build 和 PyInstaller；不新增本机环境，本批继续由 GitHub Actions 验证。
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
| 详情补充字段语义 | 时间线指纹第四项一度被标成角度，实际是 `connection_condition` | 按投影字段契约改为连接条件，并同步双语断言 |

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
- 远程绿色基线固定为 `38c3d7884a7941cc080bbfe22bbc47ccc5d0c759` / run `31672669445`，任何未提交改动都必须由自己的精确 SHA 重新通过 Actions，不能继承该绿灯。
- 当前工作树除三份规划文件外，还存在实际进度/字幕导入相关的未提交源码改动；来源已由会话交接说明确认，但尚未完成静态审计、测试配套或远程验证，因此保持在研状态且不覆盖。
- 后续执行模型固定为本地静态审计和编辑、`git diff --check`、提交、使用本机凭据推送、等待并审计同 SHA GitHub Actions；本地不执行任何构建、测试、lint、类型检查、依赖安装或打包。
- 发布候选必须在同一 SHA 上闭环 CI、Windows Package、ZIP/SHA256、许可证、版本一致性和最终 EXE 视觉证据，再创建 `v1.0.0` tag/Release。

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

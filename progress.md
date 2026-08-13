# 进度日志

## 会话：2026-08-13

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

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | CLI/UI 与 M6 远程验收阶段 |
| 我要去哪里？ | Windows onedir 打包、artifact 审计与 1.0 发布 |
| 目标是什么？ | 交付 GitHub 远程验证通过的 BDSubMerge 1.0 |
| 我学到了什么？ | 见 findings.md |
| 我做了什么？ | 见上方记录 |

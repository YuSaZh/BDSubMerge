# 发现与决策

## 需求
- 工具面向 Windows 11，输入 BDMV/PLAYLIST/MPLS/index.bdmv，输出外置 ASS/SSA/SRT/SUP。
- 任务书要求自动播放列表推荐、分集字幕映射、可视化时间线、多输出目标、项目复现和 CLI。
- UI 默认简体中文并支持英文，耗时任务必须在后台运行。
- 本机禁止构建、测试、lint、类型检查、依赖安装和打包；本机只做源码检查、静态搜索、Git 操作与 `git diff --check`，所有执行型验证必须提交并推送到 GitHub Actions。

## 研究发现
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
  `git@github.com:YuSaZh/BDSubMerge.git`，远程 `main` 为 `fdfddf9`；`gh` keyring 中
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

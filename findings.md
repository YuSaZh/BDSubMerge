# 发现与决策

## 需求
- 工具面向 Windows 11，输入 BDMV/PLAYLIST/MPLS/index.bdmv，输出外置 ASS/SSA/SRT/SUP。
- 任务书要求自动播放列表推荐、分集字幕映射、可视化时间线、多输出目标、项目复现和 CLI。
- UI 默认简体中文并支持英文，耗时任务必须在后台运行。
- 本地禁止任何构建和测试，全部验证必须通过 GitHub Actions。

## 研究发现
- GitHub 仓库为 `YuSaZh/BDSubMerge`，本机 SSH 和 Credential Manager 均可提供已有凭据。
- 当前已推送 M5 核心远程验证：run `31627068738` 的 Ubuntu、Windows、源码包任务全部成功。
- M1-M4 的领域逻辑与输出边界已经实现，当前缺口集中在 M5 集成、CLI、UI、打包与完整验收。
- Shinya 官方导入为 `shinya.bd.MoviePlaylistFile`；匿名 MPLS0200 二进制夹具固定了
  `0.2a1`（上游 commit `53998916`）的真实解析字段契约。
- SUP 时长现在优先采用“可见 PCS 之后的零对象 PCS”清屏 PTS；没有可靠清屏段时回退到最大 packet PTS 并标记为估算。
- 当前 PGS 平移按任务书将 packet 的 PTS/DTS 字段统一加偏移，包括数值为零的字段；如真实夹具显示零 DTS 是缺省语义，再以契约测试调整。
- BDMV 目录只做存在性检查；目录 mtime 会被合法生成的 `index.ass` 改变，因此输入变化判断以 index、MPLS 和字幕文件指纹为准。
- 输出目标可能尚不存在，恢复时必须无条件优先项目相对路径；源文件则只有相对候选存在时才优先，二者使用独立解析 API。
- 用户边界与自动边界同刻时会被规范化为一个候选；应用层需把持久化锁的原始边界 ID 映射到规范 ID，避免恢复失败。

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
- GitHub Actions run `31627068738`：M5 核心在 Windows、Ubuntu 与 source distribution 全部成功。
- GitHub Actions run `31630779273`：source distribution 成功；Ubuntu 与 Windows
  均只在 Ruff 阶段因同一组 16 项诊断失败，后续 Mypy、Pytest 和 UI 截图未执行。
- Ruff 修复提交 `f8c0552` 已推送；run `31659484298` 将诊断缩小为 2 项
  确定性排序问题，两个平台结果一致。
- Codex 沙箱的 Windows OpenSSH 默认解析到 `C:\Users\CodexSandboxOnline\.ssh`，会导致
  GitHub 主机密钥校验失败。Git 操作必须显式使用 `C:\Users\Hanam\.ssh\config` 和
  `C:\Users\Hanam\.ssh\known_hosts`，从而调用用户现有 SSH 凭据。

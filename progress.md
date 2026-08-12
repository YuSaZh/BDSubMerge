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
- CLI、双语 PySide6 工作区、项目打开/保存、用户边界、AC-01 至 AC-10 测试正在合并。
- 已为同刻用户/自动边界补充持久化锁 ID 规范化，避免项目恢复时锁引用失效。
- 已补齐真实 Shinya MPLS 契约、AC-01 至 AC-10 直接验收、五种 GUI 输出策略与
  自定义目录/模板控件。
- 远程 Windows CI 将建立临时 SMB 共享做真实 UNC 原子写入；Windows 打包将验证
  中文路径、无 Python PATH 启动、Shinya/pysubs2 导入及许可证材料。
- 下一步统一推送，由 GitHub Actions 验证 CLI/UI/acceptance 与无头截图。

## 远程测试结果
| GitHub run | 平台/任务 | 实际结果 | 状态 |
|------------|-----------|----------|------|
| 31624497128 | Source distribution | 构建成功 | pass |
| 31624497128 | Ubuntu Ruff/Mypy/Pytest | 64 项测试通过 | pass |
| 31624497128 | Windows | 安装依赖中 | running |
| 31624497128 | Windows 最终结果 | Ruff、Mypy、64 项测试通过 | pass |
| 31627068738 | Ubuntu、Windows、Source distribution | M5 核心全任务通过 | pass |

## 错误日志
| 阶段 | 错误 | 解决方案 |
|------|------|---------|
| M1-M4 CI | Ruff、Mypy 分轮发现问题 | 逐次按远程日志修复，未在本机执行检查 |
| Shinya contract | 缺少剪辑标识时适配器静默使用默认值 | 改为强制字段并增加契约测试 |
| 静态搜索 | PowerShell 下向 `rg` 传递文件名通配符触发 Windows 路径错误 | 改用目录参数加 `--glob` 过滤 |
| 外部资料查询 | 搜索工具返回 HTTP 500 | 不重复请求；保留任务书语义，等待真实夹具契约测试 |
| Qt 许可旧链接 | 官方义务页面旧 URL 返回 404 | 改用 Qt for Python 官方 licenses 页面与有效源码目录 |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | CLI/UI 与 M6 远程验收阶段 |
| 我要去哪里？ | Windows onedir 打包、artifact 审计与 1.0 发布 |
| 目标是什么？ | 交付 GitHub 远程验证通过的 BDSubMerge 1.0 |
| 我学到了什么？ | 见 findings.md |
| 我做了什么？ | 见上方记录 |

# BDSubMerge 开发计划

## 目标
按照项目任务书完成可发布的 BDSubMerge 1.0，并以 GitHub Actions 作为唯一构建、测试、检查和打包环境。

## 当前阶段
阶段 5：CLI 与图形界面远程验证

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
- [ ] 使用 GitHub Actions 执行 CLI/UI 测试与截图验证
- **状态：** in_progress

### 阶段 6：M6 打包、验收与发布
- [ ] 覆盖 AC-01 至 AC-10 及真实/合成夹具
- [ ] Windows onedir 打包、启动烟测与 artifact 验证
- [ ] 完善 README、用户文档、报告与未完成事项
- [ ] 完成 1.0 版本元数据和远程发布验证
- **状态：** pending

## 关键约束
1. 禁止本机构建、测试、lint、类型检查和依赖安装；需要验证时提交并推送到 GitHub Actions。
2. Git 和 GitHub 操作使用本机现有凭据，不通过浏览器重新登录。
3. 遇到异常先定位根因；不得扩大系统或仓库变更范围。

## 已做决策
| 决策 | 理由 |
|------|------|
| 内部时间统一为整数 90 kHz tick | 避免浮点误差并与 PGS PTS 直接对应 |
| 领域、应用、UI、输出分层 | 保证 GUI/CLI 不承载核心合并规则 |
| 输出必须全量预检后原子写入 | 防止部分写入和原盘损坏 |
| SUP 仅平移 packet 时间戳 | 不做 OCR、渲染或重编码，保持 payload 不变 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| 初始 CI Ruff 失败 | 1 | 按远程日志修复风格问题后重新推送 |
| 后续 CI Mypy 失败 | 1 | 修复严格类型推断后重新推送 |
| Shinya 缺少必填 ClipInformationFileName 未被拒绝 | 1 | 收紧适配器必填文本字段契约 |
| M5 远程 CI 验证 | 3 | 依次修复 Ruff 与 Mypy 后，run 31627068738 全平台通过 |

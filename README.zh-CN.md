# BDSubMerge

BDSubMerge 是一款 Windows 优先的 BDMV 原盘字幕合并工具。它只读取 BDMV 元数据，
将按集排列的 ASS、SSA、SRT 或 Blu-ray PGS SUP 字幕映射到 MPLS 播放时间线，并通过
预检和事务写入生成外挂字幕。

> 当前状态：Pre-alpha。M0-M5 的功能代码已完成，目前正由 GitHub Actions 进行集成
> 验证。这不是 1.0 正式版。

## 已实现能力

- 可从光盘目录、`BDMV`、`index.bdmv`、`PLAYLIST` 或 MPLS 路径识别原盘布局；
- 解析所有 MPLS，并以可解释分数排序，不会静默替用户选定播放列表；
- 播放列表、映射、文本字幕和 PGS 时间统一使用 90 kHz 整数 ticks；
- 保留 ASS/SSA 样式、override 样式引用、Comment、扩展段和附件；
- 支持自动分集映射、锁定映射、手动微调和用户边界；
- 所有输出先整体预检，多目标写入使用事务提交；
- 保存带源文件指纹和版本号的 `.bdsm.json` 项目；
- CLI 与正在集成的 Qt GUI 共用同一套应用服务。

## 快速开始

普通试用应使用 GitHub Actions 生成的 Windows artifact。在仓库 **Actions** 页面打开
成功的 **Package Windows** 运行，下载 `BDSubMerge-windows-x64`，完整解压后运行
`BDSubMerge.exe`。不要移动或删除同目录中的 `_internal` 文件夹。

已安装环境中的 CLI 示例：

```powershell
bdsubmerge scan "D:\Anime\Title\BDMV" --json
bdsubmerge inspect "D:\Anime\Title\BDMV\PLAYLIST\00001.mpls" --json --verbose
bdsubmerge plan "D:\Projects\Title.bdsm.json" --json
bdsubmerge validate "D:\Projects\Title.bdsm.json" --json
bdsubmerge merge "D:\Projects\Title.bdsm.json" --dry-run --json
bdsubmerge merge "D:\Projects\Title.bdsm.json" --json
```

输入、播放列表推荐、映射、输出模式、项目重定位、CLI JSON/退出码和安全规则详见
[中文用户指南](docs/user-guide.zh-CN.md)。英文文档见
[README.md](README.md) 与 [user guide](docs/user-guide.md)。

## 安全规则

- BDMV 始终只读，不会写入 `PLAYLIST`、`CLIPINF` 或 `STREAM`；
- 输出默认使用 `abort`，任一目标预检失败时不会开始写入；
- 核心时间线不使用浮点秒；
- 项目和字幕写入使用同目录临时文件与原子替换；
- 不包含遥测、源文件上传、在线字幕搜索或自动更新。

## 当前限制

- 仍需增加并验证更多真实 MPLS 与 SUP 样本；
- 真实 UNC/SMB 共享写入仍需在实际环境验证；Windows 路径解析和无网络预检已有覆盖；
- Qt GUI 尚处于集成阶段，当前不承诺稳定的 1.0 图形工作流；
- 文件移动后的项目必须先重定位并刷新指纹，才能继续合并。

## 开发与验证

目标环境为 Python 3.12。仓库规则禁止在本机执行构建、测试、lint、类型检查、依赖
安装和打包；全部验证与 Windows 打包只通过 GitHub Actions 完成。架构见
[docs/architecture.md](docs/architecture.md)，时间基准见
[docs/adr/0001-media-timebase.md](docs/adr/0001-media-timebase.md)，变更记录见
[CHANGELOG.md](CHANGELOG.md)。

## 许可证

项目采用 MIT 许可证，第三方组件声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

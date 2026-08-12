# BDSubMerge

BDSubMerge 是一款 Windows 优先的 BDMV 原盘字幕合并工具。它只读取 BDMV 元数据，
将按集制作的 ASS、SSA、SRT 或 PGS 字幕映射到 MPLS 播放时间线，并通过经过预检的
输出目标生成外挂字幕，例如 JRiver Media Center 使用的 `BDMV/index.ass`。

> 当前状态：早期开发。项目严格按照仓库内的开发任务书分里程碑实现。

## 核心约束

- 原始 BDMV 永远只读；
- 核心时间统一使用 90 kHz 整数 ticks；
- Qt、Shinya 和 pysubs2 必须通过适配层隔离；
- CLI 与 GUI 共用应用服务；
- 合并计算与输出路径解析分离；
- 默认不覆盖已有文件。

## 开发与验证

项目目标环境为 Python 3.12。根据当前开发约束，测试、静态检查和 Windows 打包
只通过 GitHub Actions 执行，禁止在本机构建。架构说明见
[docs/architecture.md](docs/architecture.md)，时间基准决策见
[docs/adr/0001-media-timebase.md](docs/adr/0001-media-timebase.md)。

## 许可证

项目采用 MIT 许可证，第三方组件声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

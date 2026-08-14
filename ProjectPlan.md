# BDSubMerge：BDMV 原盘字幕合并工具实现任务书

## 1. 项目概述

开发一款 Windows 优先、带现代图形界面的 BDMV 原盘字幕合并工具，暂定名为 **BDSubMerge**。

工具读取 Blu-ray 原盘中的 MPLS 播放列表，解析 PlayItem、IN/OUT Time、章节标记等信息，将多份 BDRip 分集字幕按原盘播放时间线重新定位并合并，最终输出一份与指定 MPLS 匹配的外挂字幕。

项目需要完整覆盖 BluraySubtitle 现有“Merge Subtitles”模块的主要能力，并重点增强：

1. 更可靠、透明的 MPLS 时间线解析；
2. 更强的分集字幕自动映射算法；
3. 可视化时间线和人工校正；
4. 更安全的 ASS/SSA 样式合并；
5. 自由配置字幕输出目录和文件名；
6. 内置 JRiver Media Center 输出模式；
7. 项目保存、批处理、日志和可复现合并；
8. 易于普通用户使用的中文图形界面。

本任务中的“功能对齐”仅指 BluraySubtitle 的字幕合并功能，不包括其 Remux、Encode、添加章节或修改 BDMV 等其他模块。

---

## 2. 产品目标

### 2.1 核心目标

用户完成一次字幕合并时，应只需要：

1. 选择原盘目录、`BDMV` 目录或 `index.bdmv`；
2. 从自动推荐结果中确认 MPLS；
3. 添加分集字幕文件；
4. 点击“自动映射”；
5. 在时间线中检查各集起止位置；
6. 选择输出模式；
7. 预检无误后生成字幕。

### 2.2 适用场景

主要适用于：

- 动漫 Blu-ray 原盘；
- 一张盘包含多集正片；
- BDRip 字幕按 E01、E02、E03 分开；
- 原盘通过一个 Play All MPLS 串联多集；
- 一集由多个 M2TS/PlayItem 组成；
- 通用 OP、ED、Logo 等片段被重复引用；
- 需要为 JRiver Media Center 生成 `index.ass`；
- 需要保留完整 ASS 特效、样式和字体引用；
- 多卷 Blu-ray 需要连续处理。

### 2.3 非目标

第一版不实现：

- 修改、重封装或写回 BDMV；
- 向原盘菜单内注册字幕轨；
- 将 ASS 渲染成 PGS；
- OCR；
- Sushi、alass 一类音频自动对轴；
- Blu-ray ISO 直接挂载；
- BD-J 菜单逆向分析；
- 视频播放和字幕画面预览；
- 在线字幕搜索和下载。

工具只读取原盘元数据，并生成外挂字幕文件，不得修改任何原始 BDMV 文件。

---

## 3. 参考项目与技术依据

### 3.1 BluraySubtitle

BluraySubtitle 当前提供了加载 Blu-ray 文件夹、加载字幕目录、检查字幕路径/时长/章节映射、调整字幕顺序并执行合并的完整流程，现有合并功能支持 ASS、SSA、SRT 和 SUP。项目使用 Python 和 Qt 图形界面，并采用 MIT 许可证。

其现有实现包含 ASS 样式冲突处理、字幕整体时间偏移、SUP 数据处理等逻辑，但输出路径与合并代码耦合，当前会将结果写到预设位置。因此新项目可以参考其算法，但必须将“字幕合并”和“输出路径策略”彻底解耦。

### 3.2 Shinya

Shinya 是用于解析和编辑 BDMV 组件的 Python 库，可处理 MPLS、CLPI 等结构，采用 MIT 许可证；其公开文档尚不完整，因此新项目必须通过独立适配层隔离 Shinya 的内部数据结构，并用测试固定实际行为。

### 3.3 pysubs2

pysubs2 可读取、编辑、平移和输出 ASS、SSA、SRT 等文本字幕格式，采用 MIT 许可证，适合作为文本字幕的语义处理基础。不得假定任意 ASS 经一次 load/save 后都能无损保留所有 Aegisub 扩展数据，必须为复杂 ASS 编写保留性测试和必要的补充解析层。

### 3.4 UI 与打包

桌面界面建议使用 PySide6 QtWidgets。PySide6 是 Qt 官方 Python 绑定，可用于跨平台桌面应用；最终 Windows 版本使用 PyInstaller 生成独立程序。Qt 官方文档明确提供 PySide6 与 PyInstaller 的部署方案。

---

## 4. 技术选型

### 4.1 基础技术栈

- Python 3.12；
- PySide6；
- Shinya；
- pysubs2；
- PyInstaller；
- pytest；
- pytest-qt；
- ruff；
- mypy；
- `pathlib`；
- `dataclasses` 或 Pydantic，用于项目文件和领域模型；
- `pyproject.toml` 管理项目；
- 使用锁文件固定依赖版本。

### 4.2 发布平台

第一阶段：

- Windows 10、Windows 11；
- x86-64；
- 提供免安装压缩包；
- 优先采用 PyInstaller `onedir` 打包；
- 不要求用户自行安装 Python。

核心代码不得依赖 Windows 专属 API，以便后续支持 Linux。

### 4.3 路径要求

必须正确支持：

- 中文、日文和其他 Unicode 路径；
- 空格；
- 长路径；
- 本地盘符；
- SMB/UNC 路径，例如：

```text
\\hpserver\storage\Anime\Title\BDMV
```

不得通过字符串拼接构造路径，统一使用 `pathlib.Path` 或等效抽象。

---

## 5. 总体架构要求

采用分层架构，核心业务逻辑不得依赖 Qt。

```text
src/
└── bdsubmerge/
    ├── app.py
    ├── cli.py
    ├── domain/
    │   ├── models.py
    │   ├── timebase.py
    │   ├── errors.py
    │   └── validation.py
    ├── bdmv/
    │   ├── layout.py
    │   ├── shinya_adapter.py
    │   ├── timeline.py
    │   ├── playlist_ranker.py
    │   └── equivalence.py
    ├── subtitles/
    │   ├── loader.py
    │   ├── text_adapter.py
    │   ├── ass_document.py
    │   ├── style_merger.py
    │   ├── pgs_adapter.py
    │   └── encoding.py
    ├── mapping/
    │   ├── boundaries.py
    │   ├── optimizer.py
    │   └── confidence.py
    ├── merge/
    │   ├── plan.py
    │   ├── engine.py
    │   └── report.py
    ├── output/
    │   ├── targets.py
    │   ├── naming.py
    │   ├── preflight.py
    │   └── atomic_writer.py
    ├── project/
    │   ├── schema.py
    │   └── persistence.py
    └── ui/
        ├── main_window.py
        ├── viewmodels/
        ├── widgets/
        ├── dialogs/
        └── resources/

tests/
├── unit/
├── integration/
├── golden/
├── ui/
└── fixtures/
```

### 5.1 强制解耦规则

- UI 不得直接访问 Shinya 原始对象；
- UI 不得直接调用 pysubs2；
- 输出路径不得写在字幕合并器内部；
- 文件写入与合并计算必须分开；
- 自动映射算法必须可在无 UI 环境下测试；
- CLI 与 GUI 必须调用同一套 application service；
- 不得为 GUI 和 CLI 各写一套合并逻辑。

---

## 6. 原盘定位与目录扫描

### 6.1 可接受的输入

用户可以选择或拖入：

- 包含 `BDMV` 文件夹的光盘根目录；
- `BDMV` 文件夹本身；
- `index.bdmv`；
- 单个 `.mpls` 文件；
- 包含多张原盘的上级目录。

### 6.2 BDMV 自动发现

输入目录后：

1. 先检查当前目录是否存在 `index.bdmv`；
2. 再检查当前目录下是否存在 `BDMV/index.bdmv`；
3. 必要时向下搜索，默认最大深度为 3；
4. 如果找到多个 BDMV，显示选择窗口；
5. 不得默认选择第一个结果；
6. 记录实际 `index.bdmv` 绝对路径。

需要兼容：

```text
Title/
└── BDMV/
    └── index.bdmv
```

以及：

```text
Title/
└── BDROM/
    └── BDMV/
        └── index.bdmv
```

### 6.3 扫描范围

扫描：

- `index.bdmv`；
- `MovieObject.bdmv`，如存在；
- `PLAYLIST/*.mpls`；
- 必要的 `CLIPINF/*.clpi`；
- 只检查 `STREAM/*.m2ts` 是否存在，不读取视频内容。

扫描时不得对几十 GB 的 M2TS 做哈希或逐个读取。

---

## 7. MPLS 解析与统一时间基准

### 7.1 内部时间单位

整个核心使用整数 **90,000 ticks/second** 作为统一时间单位，类型名建议为：

```text
MediaTick90k
```

原因：

- MPLS 的 45 kHz 时间值乘以 2 后可精确转换；
- ASS/SSA 的 10 ms 精度对应 900 ticks；
- SRT 的 1 ms 精度对应 90 ticks；
- PGS/SUP 原生使用 90 kHz PTS；
- 可以避免 float 累积误差。

禁止在核心时间线计算中使用浮点秒数。

### 7.2 PlayItem 逻辑时间线

对于每个 PlayItem：

```text
duration_90k =
    (OUTTime_45k - INTime_45k) × 2

logical_start_90k =
    前面所有 PlayItem duration_90k 的累加

logical_end_90k =
    logical_start_90k + duration_90k
```

章节标记的播放列表绝对位置：

```text
chapter_90k =
    referenced_play_item.logical_start_90k
    + (MarkTimeStamp_45k - referenced_play_item.INTime_45k) × 2
```

Shinya 适配层负责将底层 MPLS 字段转换为项目自己的不可变领域模型，不允许其他模块依赖 Shinya 的字典键或内部类。MPLS 中 PlayItem 的 IN/OUT 时间和章节引用关系应通过契约测试固定。

### 7.3 必须解析的字段

每个播放列表至少取得：

- MPLS 文件名；
- 总播放时长；
- PlayItem 数量；
- 每个 PlayItem 的 Clip ID；
- Codec Identifier；
- IN Time；
- OUT Time；
- Connection Condition；
- 是否多角度；
- 章节/Playlist Mark；
- 章节引用的 PlayItem；
- 唯一 Clip 数量；
- Clip 重复次数；
- 引用的 M2TS/CLPI 是否存在；
- Primary PG 流概况，供信息展示，不参与合并。

### 7.4 多角度处理

- 默认使用第一主角度；
- 检测到 Multi-Angle 时必须显示警告；
- UI 提供角度选择；
- 不得在未提示用户的情况下自动混用不同角度。

### 7.5 异常验证

需要检测：

- `OUTTime <= INTime`；
- 章节引用不存在的 PlayItem；
- 章节时间早于 PlayItem IN Time；
- 章节时间晚于 PlayItem OUT Time；
- 缺失的 M2TS；
- 缺失的 CLPI；
- 重复或无序章节；
- 总时长为零；
- 无法完整解析的 MPLS。

解析单个 MPLS 失败不应导致整个扫描终止，应将该 MPLS 标为“不可用”并显示错误原因。

---

## 8. 主播放列表识别

### 8.1 自动推荐而非强制选择

工具应对所有 MPLS 计算推荐分数，但不得静默锁定某个结果。

播放列表表格显示：

- 文件名；
- 时长；
- PlayItem 数；
- 章节数；
- 唯一 Clip 数；
- 重复率；
- 是否多角度；
- 引用文件完整性；
- 推荐分数；
- 推荐原因；
- 置信度。

### 8.2 推荐因素

评分至少考虑：

- 总时长；
- 正片长度阈值；
- PlayItem 和章节数量；
- 唯一 Clip 覆盖量；
- Clip 重复率；
- 是否存在明显循环；
- 是否包含大量极短片段；
- 是否更接近全部分集字幕的累计时长；
- 能否被合理划分为与字幕数量一致的连续区间。

不得仅依据“最长 MPLS”判定主播放列表。

### 8.3 播放列表等价性

实现 Timeline Fingerprint：

```text
[
  (clip_id, in_time, out_time, selected_angle),
  ...
]
```

若两个 MPLS 的有效播放序列完全一致，则标为“时间线等价”。

此功能用于：

- 合并重复播放列表；
- 解释推荐结果；
- 判断一份外挂字幕能否同时匹配多个 MPLS；
- 检测 JRiver 模式下的潜在兼容问题。

---

## 9. 字幕导入

### 9.1 支持格式

1.0 版本必须支持：

- `.ass`；
- `.ssa`；
- `.srt`；
- `.sup`，仅限 Blu-ray PGS SUP。

同一个合并任务内的字幕必须属于同一格式。

默认拒绝：

- ASS 与 SRT 混合；
- 文本字幕与 SUP 混合；
- 非 PGS 的 `.sup`；
- 无法确认格式的文件。

后续版本可以增加“全部转换为 ASS”，但不属于 1.0 必须功能。

### 9.2 添加方式

支持：

- 添加单个文件；
- 添加多个文件；
- 添加整个目录；
- 拖放；
- 从目录递归搜索；
- 删除选中项；
- 上移、下移；
- 拖动排序；
- 自然排序；
- 根据文件名提取 E01、EP01、01、Vol.1 等序号；
- 一键恢复自然排序。

### 9.3 字幕信息分析

每个文件显示：

- 文件名；
- 格式；
- 编码；
- 事件数；
- 样式数；
- 最早开始时间；
- 原始最晚结束时间；
- 用于自动匹配的有效结束时间；
- PlayResX/PlayResY；
- 是否含字体附件；
- 是否含图形附件；
- 是否含 Aegisub Extradata；
- 警告数量。

### 9.4 编码识别

文本字幕至少支持：

- UTF-8；
- UTF-8 BOM；
- UTF-16 LE/BE；
- GB18030；
- Shift-JIS。

自动识别置信度不足时要求用户选择，不得静默用错误编码打开后再覆盖文件。

---

## 10. 字幕有效时长估算

有效时长只用于自动映射，不得因此删除原始事件。

### 10.1 文本字幕

默认使用非 Comment 事件中的最大结束时间。

同时显示：

- Raw End：所有事件的最大结束时间；
- Effective End：自动匹配使用的结束时间。

### 10.2 异常长事件

如果最后一个事件比倒数第二个有效事件晚超过默认 300 秒：

- 将其标记为疑似异常事件；
- 自动匹配默认使用倒数第二个事件估算时长；
- 合并输出仍然保留该事件；
- UI 允许用户切换为使用 Raw End；
- 不得静默删除或裁剪。

### 10.3 SUP

SUP 有效时长根据 PGS Display Set 的 PTS 和清屏信息估算。

无法准确推断结束时间时：

- 显示“估算”标记；
- 降低自动映射置信度；
- 允许用户手动指定该字幕的参考时长。

---

## 11. 时间线边界模型

自动生成以下候选边界：

- 播放列表起点；
- 播放列表终点；
- 每个 PlayItem 起点；
- 每个 PlayItem 终点；
- Playlist Mark/章节；
- 用户手动添加的边界。

每个边界保存：

- 90 kHz 时间值；
- 显示时间；
- 来源；
- 引用的 PlayItem；
- 引用的 Clip；
- 边界可信度；
- 是否启用；
- 用户备注。

重复边界按时间容差合并，但应保留所有来源信息。

---

## 12. 分集字幕自动映射

### 12.1 映射结果

每个字幕文件对应一个 `EpisodeMapping`：

- 字幕文件；
- 目标 MPLS；
- 起始边界；
- 结束边界；
- 起始偏移；
- 额外微调；
- 目标区间时长；
- 自动匹配分数；
- 置信度；
- 警告；
- 是否由用户锁定。

最终字幕事件的偏移：

```text
final_time =
    original_time
    + episode_start_90k
    + manual_offset_90k
```

### 12.2 自动映射算法

不要使用简单的逐集贪心匹配。

实现基于动态规划的有序区间匹配：

- 输入 N 个有序字幕；
- 输入 B 个有序候选边界；
- 为每个字幕选择一个起始边界和结束边界；
- 区间必须单调且不得倒序；
- 默认不允许分集区间互相重叠；
- 可以允许两集之间存在未映射片段；
- 可以跨越多个 PlayItem；
- 用户锁定的映射不得被重新计算。

概念成本函数：

```text
总成本 =
    字幕与区间时长适配成本
    + 边界来源惩罚
    + 跳过区间惩罚
    + 重叠惩罚
    + 超出播放列表惩罚
    + 异常短区间惩罚
```

时长适配应采用非对称惩罚：

- 字幕有效结束时间略早于区间结束是正常情况；
- 字幕事件明显超出目标区间应受到更高惩罚；
- 不应要求字幕最后一句对白精确落在集末。

### 12.3 置信度

输出：

- 高；
- 中；
- 低。

低置信度时：

- 显示醒目警告；
- 默认禁止直接批量合并；
- 用户明确确认后才能继续。

### 12.4 手动编辑

用户必须可以：

- 为每集选择起始边界；
- 为每集选择结束边界；
- 输入毫秒级微调；
- 在时间线中拖动字幕区间；
- 吸附到章节或 PlayItem 边界；
- 锁定一集后重新计算其他集；
- 批量增加或减少延迟；
- 指定某些原盘片段不对应字幕；
- 重置为自动结果。

---

## 13. 可视化时间线

使用 Qt `QGraphicsView` 或等效高性能组件。

时间线至少包含：

- MPLS 全长标尺；
- PlayItem 区块；
- Clip ID；
- 章节刻度；
- 分集字幕区间；
- 未映射区间；
- 冲突和超界提示；
- 当前选择项；
- 缩放；
- 横向滚动；
- 鼠标悬停信息；
- 时间格式切换。

时间显示支持：

```text
HH:MM:SS.mmm
HH:MM:SS:FF
90 kHz ticks
```

拖动映射边界时：

- 默认吸附候选边界；
- 按住修饰键可关闭吸附；
- 只能修改映射，不得直接修改原始字幕事件；
- 修改后实时重新计算警告。

---

## 14. ASS/SSA 合并要求

这是项目最重要的部分之一。

### 14.1 基本原则

- 保留每个源字幕的事件；
- 保留原始事件顺序；
- 按分集顺序追加；
- 对所有需要保留的事件执行时间偏移；
- 默认不做全局按时间排序；
- 不改写字幕正文中的其他 override tags；
- 不改变绘图、卡拉 OK、移动、渐变和定位标签。

### 14.2 事件类型

默认保留并平移：

- Dialogue；
- Comment。

用于估算时长时默认忽略 Comment，但输出时保留。

### 14.3 样式冲突规则

#### 相同名称、相同定义

只保留一份。

#### 相同名称、不同定义

必须确定性重命名，例如：

```text
Default
Default__E02
Default__E03
Default__E03_2
```

命名不得依赖随机数或运行顺序之外的状态。

重命名后必须同步修改：

- Event 的 Style 字段；
- 文本中的 `\rStyleName`；
- 其他明确引用样式名的受支持结构。

仅使用简单字符串替换是不允许的，应解析 ASS override block，仅替换完整的样式引用。

### 14.4 Script Info

以第一份字幕或用户指定字幕作为基础 Script Info。

以下字段不一致时必须显示警告：

- PlayResX；
- PlayResY；
- WrapStyle；
- ScaledBorderAndShadow；
- YCbCr Matrix；
- Timer。

分辨率不一致时默认阻止无提示合并。用户可以：

- 选择以某一文件为基础；
- 明确接受不做坐标变换；
- 后续版本再实现可选的坐标和样式缩放。

第一版不得假装已自动解决分辨率不一致。

### 14.5 ASS 扩展段保留

需要正确保留或合并：

- `[Script Info]`；
- `[V4 Styles]`；
- `[V4+ Styles]`；
- `[Events]`；
- `[Aegisub Project Garbage]`；
- `[Aegisub Extradata]`；
- `[Fonts]`；
- `[Graphics]`；
- 未识别的自定义 section。

对未识别 section：

- 不得无提示丢弃；
- 应保留原始文本；
- 多文件冲突时显示报告。

### 14.6 Aegisub Extradata

如果多个字幕使用相同 Extradata ID：

- 根据内容去重；
- 内容不同则分配新 ID；
- 修改对应事件中的 Extradata 引用；
- 保证合并后引用不串集。

### 14.7 字体和图形附件

- 按附件名和内容哈希去重；
- 同名不同内容时确定性重命名；
- 保留编码数据；
- 在报告中列出附件合并结果。

### 14.8 Format 字段

不同 ASS 文件可能使用不同字段顺序。

解析时必须按 `Format:` 声明映射字段，不得假设固定列顺序。

输出时可以统一为标准字段顺序，但不得丢失受支持字段。

### 14.9 时间边界处理

事件偏移后：

- `end <= 0`：默认丢弃并记录；
- `start < 0 < end`：默认将 start 截至 0，并记录；
- `end > playlist_end`：默认保留但警告；
- `start > playlist_end`：默认保留但作为严重警告；
- `end < start`：阻止输出。

提供高级选项：

- 保留超界事件；
- 裁剪到分集区间；
- 裁剪到播放列表范围；
- 删除完全超界事件。

默认不得裁剪分集区间，因为部分 OP、ED 或特效可能有意跨越边界。

### 14.10 序列化精度

内部时间保持 90 kHz 整数。

输出 ASS/SSA 时：

- 开始时间向下取整到 10 ms；
- 结束时间向上取整到 10 ms；
- 确保序列化后 `end > start`。

输出 SRT 时：

- 开始时间向下取整到 1 ms；
- 结束时间向上取整到 1 ms。

---

## 15. SRT 合并要求

- 保留字幕文本；
- 保留换行；
- 平移时间；
- 重新连续编号；
- 不要求保留原编号；
- 输出标准 SRT 时间格式；
- 可选 UTF-8 或 UTF-8 BOM；
- 默认 UTF-8 BOM；
- 对重叠只警告，不自动合并或删除。

---

## 16. SUP/PGS 合并要求

### 16.1 实现方式

SUP 合并为二进制时间平移，不进行 OCR、渲染或重新编码。

需要：

- 解析每个 PGS packet；
- 识别 PTS/DTS；
- 将分集起始偏移加到所有相关时间戳；
- 保持 segment payload 不变；
- 按字幕文件顺序追加；
- 验证 packet 完整性；
- 输出合法 SUP。

### 16.2 时间基准

SUP 使用 90 kHz PTS，与内部统一时间基准直接对应。

### 16.3 异常情况

检测并报告：

- 无效 `PG` magic；
- packet 长度越界；
- PTS/DTS 溢出；
- 非单调时间戳；
- 缺失 END segment；
- 不支持的 SUP 结构。

可以参考或适配 BluraySubtitle 的 MIT 代码，但如复制或修改其实现，必须保留对应许可证和版权声明。

---

## 17. 输出系统

### 17.1 输出策略接口

字幕合并引擎只返回合并结果，不决定保存位置。

定义统一接口：

```text
OutputTarget
- resolve_paths(context)
- validate(context)
- describe()
- collision_policy
- encoding
```

一个任务允许同时启用多个输出目标。

### 17.2 内置输出模式

#### 模式 A：JRiver Media Center

以实际扫描到的 `index.bdmv` 路径为准：

```text
output_path =
    index_bdmv_path.with_suffix(subtitle_extension)
```

示例：

```text
\\hpserver\storage\Anime\Title\BDMV\index.bdmv
```

ASS 输出必须是：

```text
\\hpserver\storage\Anime\Title\BDMV\index.ass
```

要求：

- 与实际 `index.bdmv` 同目录；
- 基础文件名严格为 `index`；
- 默认不添加 `.zh`、`.chs`、语言代码或 MPLS 名；
- UI 明确显示完整目标路径；
- JRiver 模式禁止“自动改名”，因为改名会破坏匹配；
- 找不到 `index.bdmv` 时禁止启用；
- 一个 BDMV 只能指定一个 JRiver 主输出任务。

不要把“光盘根目录”写死，必须根据实际发现的 `index.bdmv` 路径计算。

#### 模式 B：MPLS 同名

```text
<BDMV>/PLAYLIST/<playlist_stem>.<ext>
```

示例：

```text
BDMV/PLAYLIST/00000.ass
```

允许可选语言后缀：

```text
00000.zh-Hans.ass
```

#### 模式 C：原盘文件夹同名

根据所识别的光盘容器文件夹名称输出到其父目录或指定目录。

示例：

```text
Title.ass
```

#### 模式 D：自定义目录

用户选择任意目录和文件名模板。

支持变量：

```text
{disc_name}
{playlist}
{playlist_stem}
{index_stem}
{language}
{format}
{volume}
```

示例：

```text
{disc_name}_{playlist}_{language}.{format}
```

#### 模式 E：指定完整文件路径

用户直接选择最终文件名。

### 17.3 多 MPLS 与 JRiver 冲突

如果用户选择多个非等价 MPLS：

- 可以为每个 MPLS输出各自同名字幕；
- 但只能有一个 MPLS生成 `index.ass`；
- UI 要求用户指定“JRiver 主时间线”；
- 如果菜单可能播放其他非等价 MPLS，显示以下警告：

```text
一份 index.ass 只能对应一条播放时间线。
当前原盘包含多个不等价播放列表，从菜单进入其他标题时，
该字幕可能无法正确匹配。
```

如果多个 MPLS 时间线等价，可以标注为兼容。

### 17.4 文件冲突策略

支持：

- 中止；
- 覆盖；
- 覆盖前备份；
- 自动改名。

默认：

```text
中止整个任务
```

JRiver 模式只允许：

- 中止；
- 覆盖；
- 覆盖前备份。

### 17.5 原子写入

所有输出必须：

1. 先在目标目录写临时文件；
2. 完成后 flush；
3. 验证输出；
4. 使用同文件系统原子替换；
5. 失败时删除临时文件；
6. 不留下半成品。

批量任务开始前必须预检全部目标路径。

如果任意目标存在阻断错误，默认一个文件也不写。

---

## 18. 合并预检

点击“生成”前显示预检页面。

至少检查：

- BDMV 和 MPLS 是否仍存在；
- MPLS 文件大小和修改时间是否变化；
- 字幕源文件是否变化；
- 映射是否单调；
- 是否存在未映射字幕；
- 是否存在无字幕区间；
- 是否有时间重叠；
- 是否有超界事件；
- ASS 样式冲突是否已解决；
- Script Info 是否冲突；
- 输出格式是否一致；
- 目标目录是否可写；
- 目标文件是否存在；
- JRiver 文件名是否严格正确；
- 输出路径是否与任何输入字幕相同；
- 多个输出目标是否互相覆盖。

预检结果分为：

- 错误：禁止输出；
- 警告：用户确认后输出；
- 信息：无需确认。

---

## 19. UI 设计要求

### 19.1 界面语言

- 默认简体中文；
- 支持英文；
- 所有文本通过翻译资源管理；
- 不得把中文字符串散落在业务逻辑中。

### 19.2 主窗口布局

建议采用单窗口分步工作区，而不是强制向导，以便来回调整。

```text
┌─────────────────────────────────────────────────────┐
│ 原盘路径 [____________________] [选择] [重新扫描]   │
├───────────────┬─────────────────────────────────────┤
│ 播放列表列表  │ 播放时间线                          │
│               │ PlayItem / Chapter / Episode        │
├───────────────┴─────────────────────────────────────┤
│ 分集字幕映射表                                      │
├─────────────────────────────────────────────────────┤
│ 输出模式、完整目标路径、预检结果                    │
├─────────────────────────────────────────────────────┤
│ [保存项目] [自动映射] [预检] [生成字幕]             │
└─────────────────────────────────────────────────────┘
```

### 19.3 播放列表表格

支持：

- 排序；
- 筛选；
- 搜索 MPLS 编号；
- 单选和多选；
- 双击查看结构；
- 右键导出解析信息；
- 推荐项置顶，但不自动隐藏其他项。

### 19.4 字幕映射表格

列至少包括：

- 序号；
- 字幕文件；
- 格式；
- 有效时长；
- 起始边界；
- 结束边界；
- 目标区间时长；
- 微调；
- 置信度；
- 状态；
- 警告。

支持：

- 拖动排序；
- 多选；
- 批量偏移；
- 锁定；
- 自动映射未锁定项；
- 跳转到时间线；
- 查看源字幕详情。

### 19.5 输出区域

显示：

- 输出模式；
- 完整目标路径；
- 编码；
- 冲突策略；
- 是否备份；
- 输出格式；
- 预计事件数量；
- 预计样式数量；
- 警告摘要。

不得只显示“已选择 JRiver 模式”，必须显示最终完整文件路径。

### 19.6 后台任务

扫描、解析和合并不得阻塞 UI。

使用后台任务执行：

- BDMV 扫描；
- 大量 MPLS 解析；
- 字幕目录扫描；
- ASS 附件分析；
- SUP 解析；
- 输出生成。

界面需要：

- 进度；
- 当前处理文件；
- 取消按钮；
- 错误详情；
- 完成摘要。

取消后不得留下临时输出。

### 19.7 易用性

- 支持拖放；
- 记忆最近路径；
- 记忆窗口尺寸；
- 记忆输出模式；
- 系统、浅色、深色主题；
- 高 DPI；
- 键盘操作；
- 清晰的错误文本；
- 避免连续弹出多个模态窗口；
- 高级选项默认折叠。

---

## 20. 项目文件

### 20.1 格式

项目文件扩展名建议：

```text
.bdsm.json
```

包含：

- schema version；
- BDMV 实际路径；
- `index.bdmv` 路径；
- 所选 MPLS；
- MPLS 指纹；
- 字幕列表；
- 字幕文件元数据；
- 排序；
- 映射边界；
- 微调；
- 用户锁定状态；
- 输出目标；
- 冲突策略；
- 编码；
- UI 备注。

### 20.2 路径保存

- 项目与字幕位于同一树下时优先保存相对路径；
- 同时保留必要的路径恢复信息；
- 打开项目时检测文件变化；
- 不得因盘符变化直接崩溃；
- 文件缺失时允许用户重新定位。

### 20.3 Schema 升级

必须包含：

```text
schema_version
```

后续版本通过迁移函数升级，禁止直接假定旧项目与新模型完全一致。

---

## 21. CLI

即使主要面向 GUI，也必须提供最小 CLI，以便测试和批处理。

建议命令：

```text
bdsubmerge scan <path>
bdsubmerge inspect <mpls>
bdsubmerge plan <project.bdsm.json>
bdsubmerge merge <project.bdsm.json>
bdsubmerge validate <project.bdsm.json>
```

支持：

- `--json`；
- `--dry-run`；
- `--verbose`；
- 合理的退出码；
- 无交互运行。

GUI 必须调用与 CLI 相同的应用服务。

---

## 22. 领域模型

至少定义以下不可变或受控模型。

### `BdmvLayout`

- selected_path；
- disc_container_path；
- bdmv_path；
- index_bdmv_path；
- playlist_path；
- clipinf_path；
- stream_path。

### `PlaylistInfo`

- path；
- stem；
- duration_90k；
- play_items；
- marks；
- warnings；
- score；
- confidence；
- timeline_fingerprint。

### `PlayItemInfo`

- index；
- clip_id；
- codec_id；
- in_time_45k；
- out_time_45k；
- logical_start_90k；
- logical_end_90k；
- connection_condition；
- angle 信息；
- 文件存在状态。

### `TimelineBoundary`

- id；
- time_90k；
- kinds；
- source references；
- confidence；
- enabled；
- user_created。

### `SubtitleAsset`

- path；
- format；
- encoding；
- events；
- raw_end_90k；
- effective_end_90k；
- metadata；
- warnings；
- source fingerprint。

### `EpisodeMapping`

- subtitle；
- playlist；
- start_boundary；
- end_boundary；
- manual_offset_90k；
- locked；
- confidence；
- warnings。

### `OutputTarget`

- preset；
- path template；
- resolved path；
- encoding；
- collision policy；
- backup policy。

### `MergePlan`

- source snapshot；
- playlist；
- ordered mappings；
- merge options；
- output targets；
- warnings；
- blocking errors。

---

## 23. 日志与报告

### 23.1 运行日志

默认保存到用户应用数据目录，不写入原盘目录。

记录：

- 软件版本；
- Python 和依赖版本；
- 原盘路径；
- MPLS；
- 字幕列表；
- 映射结果；
- 输出路径；
- 样式重命名；
- 附件去重；
- 超界事件；
- 文件冲突；
- 错误堆栈。

不得记录字幕正文内容，除非用户主动开启调试模式。

### 23.2 合并报告

每次成功合并生成可选 JSON 或文本报告：

- 使用的播放列表；
- PlayItem 时间线；
- 每集起止时间；
- 微调；
- 原始和有效字幕时长；
- 输出文件；
- 事件数量；
- 样式重命名表；
- 警告；
- 源文件指纹。

---

## 24. 安全与数据保护

强制要求：

- BDMV 只读；
- 不写入 `PLAYLIST`、`CLIPINF`、`STREAM` 等原始文件；
- 不重命名原始字幕；
- 不覆盖源字幕；
- 不发送网络请求；
- 不包含遥测；
- 不自动下载更新；
- 写入前显示完整目标路径；
- 所有覆盖操作都必须显式配置；
- 默认遇到目标文件时中止。

---

## 25. 测试要求

### 25.1 单元测试

#### MPLS 时间线

覆盖：

- 单 PlayItem；
- 多 PlayItem；
- PlayItem 使用部分 M2TS；
- 相同 Clip 重复引用；
- 章节位于非零 IN Time；
- 章节恰好位于 PlayItem 边界；
- 重复章节；
- 无章节；
- 非法章节引用；
- Multi-Angle；
- 45 kHz 到 90 kHz 的精确转换；
- 24 集累计后无浮点漂移。

#### 自动映射

覆盖：

- 一集对应一个 PlayItem；
- 一集跨多个 PlayItem；
- 集间存在 Logo；
- 集间存在未映射片段；
- 字幕最后事件早于集末；
- 字幕异常长尾事件；
- 用户锁定部分映射；
- 无可行映射；
- 相同成本时结果确定。

#### ASS/SSA

覆盖：

- 相同样式同定义；
- 相同样式不同定义；
- 多次样式冲突；
- `\rStyleName`；
- 单独的 `\r`；
- 卡拉 OK；
- 绘图；
- Comment；
- Layer；
- 不同 Format 字段顺序；
- Aegisub Extradata ID 冲突；
- 字体附件；
- 图形附件；
- 未知 section；
- UTF-8 BOM；
- UTF-16；
- GB18030；
- 负时间；
- 超出播放列表；
- 分辨率不一致。

#### SUP

覆盖：

- 单个 Display Set；
- 多个 Display Set；
- PTS/DTS 平移；
- packet 长度错误；
- 非法 magic；
- 时间戳溢出；
- 多文件追加。

#### 输出

覆盖：

- JRiver 精确路径；
- MPLS 同名路径；
- 自定义模板；
- UNC 路径；
- 中文路径；
- 文件已存在；
- 备份；
- 原子写入；
- 中途失败无半成品；
- 多目标预检事务。

### 25.2 Golden Tests

准备人工确认过的输入与输出 fixture。

Golden Test 比较：

- 合并后的事件时间；
- 样式表；
- Extradata；
- 附件；
- 输出 section；
- JRiver 文件名；
- 合并报告。

测试数据必须自行构造或匿名化，不在仓库中加入有版权的商业原盘数据。

### 25.3 UI 测试

使用 pytest-qt 覆盖：

- 打开原盘；
- 扫描完成；
- 选择 MPLS；
- 添加字幕；
- 自动映射；
- 修改边界；
- 选择 JRiver 模式；
- 查看输出路径；
- 预检；
- 取消后台任务；
- 生成字幕。

### 25.4 打包测试

Windows 干净环境验证：

- 无 Python 环境也能启动；
- Qt 平台插件完整；
- 中文路径正常；
- UNC 路径正常；
- Shinya 和 pysubs2 均被正确打包；
- 不依赖开发机环境变量。

---

## 26. 验收标准

### AC-01：JRiver 输出

给定：

```text
D:\Anime\Title\BDMV\index.bdmv
```

用户选择 JRiver 模式并合并 ASS 后，只能生成：

```text
D:\Anime\Title\BDMV\index.ass
```

不得生成：

```text
D:\Anime\Title\index.ass
D:\Anime\Title\BDMV\index.zh.ass
D:\Anime\Title\BDMV\00000.ass
```

### AC-02：UNC 路径

给定：

```text
\\hpserver\storage\Anime\Title\BDMV\index.bdmv
```

可以扫描、预检并原子写入：

```text
\\hpserver\storage\Anime\Title\BDMV\index.ass
```

### AC-03：原盘不被修改

合并前后，所有原始：

- `.bdmv`；
- `.mpls`；
- `.clpi`；
- `.m2ts`

的大小和修改时间保持不变。

### AC-04：精确时间线

对于人工构造的 24 集播放列表：

- 每集起始时间与指定边界一致；
- 不因累计 float 产生漂移；
- ASS 输出误差不超过格式自身 10 ms 精度；
- SRT 输出误差不超过格式自身 1 ms 精度。

### AC-05：样式冲突

两份 ASS 含同名但不同定义样式时：

- 输出保留两套定义；
- 后一套被确定性重命名；
- Event Style 字段同步修改；
- `\rStyleName` 同步修改；
- 其他 override tags 不变。

### AC-06：项目复现

保存项目后关闭程序，再次打开项目并执行合并：

- 映射保持一致；
- 输出目标保持一致；
- 输入未变化时输出内容保持确定；
- 输入变化时给出明确警告。

### AC-07：文件冲突

目标存在且策略为“中止”时：

- 不覆盖目标；
- 不创建其他输出；
- 不留下临时文件。

### AC-08：低置信度

自动映射置信度低时：

- UI 明确标识；
- 默认阻止一键输出；
- 用户确认后才可继续。

### AC-09：UI 响应

扫描大量播放列表或解析 SUP 时：

- 主窗口可以移动；
- 可以切换页面；
- 可以取消任务；
- 不出现长时间“未响应”。

### AC-10：多播放列表警告

同一 BDMV 选择多个非等价 MPLS，并尝试使用 JRiver 模式时：

- 要求指定唯一 JRiver 主时间线；
- 明确提示一份 `index.ass` 无法同时匹配多条非等价时间线。

---

## 27. 开发里程碑

### M0：项目骨架

完成：

- `pyproject.toml`；
- 目录结构；
- CI；
- ruff；
- mypy；
- pytest；
- 基础日志；
- 许可证；
- `THIRD_PARTY_NOTICES.md`；
- 架构文档；
- 时间基准 ADR。

### M1：BDMV 解析核心

完成：

- BDMV 自动定位；
- Shinya 适配层；
- MPLS 扫描；
- PlayItem 时间线；
- 章节转换；
- 播放列表指纹；
- CLI `scan` 和 `inspect`；
- 单元测试。

此阶段不开发完整 UI。

### M2：文本字幕合并核心

完成：

- ASS、SSA、SRT 加载；
- 90 kHz 统一时间；
- 时间平移；
- 样式合并；
- 样式重命名；
- override 样式引用修改；
- Extradata；
- 附件；
- 编码；
- Golden Tests。

### M3：自动映射

完成：

- 候选边界；
- 动态规划；
- 置信度；
- 用户锁定；
- 合并计划；
- CLI `plan` 和 `validate`。

### M4：输出系统

完成：

- 输出策略接口；
- JRiver 模式；
- MPLS 同名模式；
- 自定义模板；
- 原子写入；
- 冲突策略；
- 备份；
- 合并报告；
- CLI `merge`。

### M5：SUP 与图形界面

完成：

- PGS/SUP 适配器；
- 主窗口；
- 播放列表表格；
- 字幕映射表；
- 时间线；
- 输出预检；
- 后台任务；
- 项目保存和加载。

### M6：1.0 发布

完成：

- 全部验收用例；
- Windows 打包；
- 干净系统测试；
- 中文使用说明；
- 英文基础翻译；
- 示例项目；
- 开发文档；
- Changelog；
- Release 包。

---

## 28. 许可证要求

- 项目自身建议使用 MIT 许可证；
- Shinya、pysubs2、BluraySubtitle 的 MIT 许可证声明必须保留；
- 复制或改写现有项目代码时，在源文件头和 `THIRD_PARTY_NOTICES.md` 中标注来源；
- PySide6 和 Qt 相关发布义务需要在发行前单独核对；
- 打包产物中包含所有必须的许可证文本；
- 不得复制无法确认许可证的论坛附件代码。

---

## 29. Codex 开发约束

Codex 必须遵守以下规则：

1. 不要直接从 UI 开始写。
2. 先建立可测试的时间线和合并核心。
3. 每个里程碑都必须有测试。
4. 不允许用 float 表示核心时间。
5. 不允许修改 BDMV。
6. 不允许把 JRiver 路径写死为“原盘根目录”。
7. 必须以实际 `index.bdmv` 的父目录和 stem 计算输出。
8. 不允许静默丢弃 ASS 未识别 section。
9. 不允许静默解决 Script Info 冲突。
10. 不允许自动覆盖已有字幕。
11. 不允许 UI 直接依赖 Shinya 数据结构。
12. 不允许 GUI 和 CLI 分别实现合并逻辑。
13. 所有自动猜测都必须显示置信度和原因。
14. 所有输出必须经过预检和原子写入。
15. 每发现一个第三方库行为不确定点，先添加契约测试，再依赖该行为。
16. 使用类型标注。
17. 重要算法写清楚注释，但不要把 UI 文案或业务规则散落在代码中。
18. 每个里程碑完成后更新 README、测试结果和未完成事项。
19. 不要为了赶进度跳过复杂 ASS 的保留性测试。
20. 遇到无法无损支持的 ASS 特性时，应明确报错或警告，不得假装成功。

---

## 30. Definition of Done

项目只有同时满足以下条件才视为 1.0 完成：

- 能读取真实 BDMV 文件夹；
- 能推荐和手动选择 MPLS；
- 能显示 PlayItem 和章节时间线；
- 能自动映射并手动调整分集字幕；
- 支持 ASS、SSA、SRT、SUP；
- ASS 样式和扩展数据通过 Golden Tests；
- 能生成与 `index.bdmv` 同级同名的 JRiver 字幕；
- 输出位置可以自由配置；
- 能保存和重新打开项目；
- 有 CLI；
- UI 在后台任务期间保持响应；
- 不修改原盘；
- 输出使用原子写入；
- Windows 免安装版本可在无 Python 环境启动；
- 全部 AC-01 至 AC-10 验收通过；
- 文档、许可证、测试和构建脚本齐全。
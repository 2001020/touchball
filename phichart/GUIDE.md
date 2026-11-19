# phichart 制谱指南（给模型看的规则书）

你要独立完成一张 **Phira 自制谱（RPE JSON 格式）**：从分析音频、规划分段与采音，到写谱、渲染自查、修改、导出。
本指南是硬性规则 + 经验法则。**先通读一遍再动手。**

---

## 0. 你手里的东西

| 路径 / 命令 | 用途 |
|---|---|
| `analysis/summary.md` | BPM、offset、自动分段、各声部 onset 数量、每小节能量 |
| `analysis/bars.txt` | **采音底稿**：每小节一行，5 个声部（kick/snare/hat/melody/bass）各 16 格（1 格 = 1/4 拍），数字 1-9 = 起音强度 |
| `analysis/overview.png` | 频谱 + 能量 + 分段总览图 |
| `PLAN.md` | 你的谱面规划（必须先写） |
| `chart.json` | 谱面本体（RPE JSON，可写"宽松格式"，见 §2.6） |
| `phichart onsets . --from A --to B [--layers melody,snare] [--min 0.3]` | 列出区间内检测到的起音（已量化到拍，含强度、延音长度 len、三连音标记 tri） |
| `phichart timeline . --from A --to B` | **编辑器视图**：音符按拍排布（时间向上），左侧并排 5 条起音泳道 K/S/H/M/B，用来核对"音符是否压在音上"、密度、形状 |
| `phichart snap . --around B` | **Phira 真引擎渲染**：B 拍前后若干时刻的实际游戏画面（默认偏移 -2,-1,-0.5,0,+0.5,+1 拍）拼成一张图 |
| `phichart snap . --beat B1,B2 ...` / `--range A B --step 0.5` | 指定拍渲染 |
| `phichart snap . --around B --compare @prev` | 上行 BEFORE（上一个检查点）/ 下行 AFTER（当前），对比修改前后 |
| `phichart splice . --from A --to B --file frag.json [--line 0]` | 用片段文件替换某条线在 [A,B) 内的全部音符（自动存检查点） |
| `phichart checkpoint . -m msg` / `phichart history .` | 手动存档 / 列出存档（`@prev`=最近一次，`@2`=倒数第二次） |
| `phichart notes . --from A --to B` | 文本列出区间音符 |
| `phichart lint .` | 可玩性/可读性/同步检查（错误必须清零） |
| `phichart fmt .` | 规范化 chart.json（补默认值、时间转三元组、排序、一行一个音符） |
| `phichart export . --pez` | 导出最终严格 RPE json（export/chart.json）和 Phira 导入包 |
| `phichart analyze . --bpm X / --offset-ms Y / --downbeat-shift N --update-chart` | 修正节拍网格（只在还没写音符时用） |

渲染输出的 PNG 都在 `renders/`，**命令打印出路径后必须真的打开图片看**（Claude Code 里用 Read 工具读 png；API 后端用 view_image）。

---

## 1. 坐标、时间、流速 —— 必须吃透的数字

### 1.1 时间
* 所有时间都是 **拍（beat）**，写成三元组 `[整数拍, 分子, 分母]` = 整数拍 + 分子/分母。`[12,1,2]` = 第 12.5 拍。**第一个数是拍，不是小节**。
* 4/4 拍：第 n 小节从第 `4n` 拍开始。小节 0 是**引导小节**（在第一个强拍之前，给开头留出读谱时间）。
* `META.offset`（毫秒）= 第 0 拍对应的音乐时间。可能为负（第 0 拍在音频开始之前），这是故意的，不要改。
* 拍 → 秒：`t = offset/1000 + beat * 60/BPM`。
* 允许的细分：1/2、1/4（16 分）、1/3、1/6（三连音）、1/8（32 分，仅限 drag 连打/装饰）。其它分母一律视为错误。

### 1.2 屏幕坐标（RPE 单位）
* 画面 16:9，x ∈ [-675, 675]，y ∈ [-450, 450]，原点在屏幕中心，**y 向上为正**。
* 判定线默认在 `y = -270`（屏幕下方约 1/5 处），水平，长度贯穿屏幕。
* `positionX` 是音符相对判定线中心、沿线方向的偏移。
* **音符宽度 ≈ 178 单位**（屏幕宽的 13%）。
  * 同时出现的两个音符中心距 **≥ 180（硬性）**，推荐 ≥ 300。
  * 音符击打点必须在屏幕内：|x| ≤ 600，主要活动区 [-500, 500]。
* 渲染图下方的标尺标出了 x = -600…600 每 150 的位置，用它把画面上的位置对应回 positionX。

### 1.3 流速（speed events）—— 决定可读性
* 速度事件的值 v：音符每秒移动 `v × 120.2` 个 RPE 单位（再乘以音符自身的 `speed` 倍率）。
* **可见时间（lead time）** = 音符从屏幕边缘出现到落到判定线的时间：
  `T = (450 − lineY) / (120.2 × v)`。判定线在 -270 时距离 720：

  | 目标可见时间 T | v（lineY=-270） | 适用 |
  |---|---|---|
  | 1.30 s | 4.6 | 很慢：开头、抒情、EZ |
  | 1.10 s | 5.4 | 偏慢：低密度段 |
  | 0.95 s | 6.3 | **默认推荐**（IN 难度主体） |
  | 0.85 s | 7.0 | 偏快：高能段/副歌 |
  | 0.72 s | 8.3 | 快：AT 级高潮，仅在模式清晰时 |
  | < 0.6 s | > 10 | 禁止（读不过来） |

* 规则：
  * 一个段落内流速**恒定**；只在段落边界、且附近 1 拍内没有密集音符时改变。
  * 用 **2 个相邻事件**表达变化：`{start:6.3,end:6.3}` 到边界，然后下一个事件 `{start:7,end:7}`；想要平滑过渡就用一个 1~2 拍的线性事件 `{start:6.3,end:7}`。
  * 密度越高 → 流速稍快（音符之间间隔更大更好读），但不要超过 0.7 s 可见时间。
  * 跨度控制在 4.6 ~ 8.3 之间；整首谱变化次数通常 2~6 次。
  * `RPEVersion` 保持 150（Phira 默认的旧速度模式：事件内线性插值）。**速度事件只用 easingType 1。**
* `phichart lint` 会对每个音符计算真实可见时间，< 0.42 s 或 > 2.4 s 报警。

---

## 2. RPE JSON 格式

### 2.1 顶层
```json
{
  "META": {"RPEVersion": 150, "offset": -1050, "name": "...", "song": "song.ogg", "charter": "...", "level": "IN Lv.12", ...},
  "BPMList": [{"bpm": 109.0, "startTime": [0,0,1]}],
  "judgeLineGroup": ["Default"],
  "judgeLineList": [ <判定线>, ... ]
}
```
不要改 `BPMList`/`offset`，除非你在 §4 步骤 2 中确认网格错误并用 `phichart analyze --update-chart` 修正。

### 2.2 判定线
```json
{
  "Name": "main", "Texture": "line.png", "father": -1, "isCover": 1, "zOrder": 0, "Group": 0, "bpmfactor": 1.0,
  "eventLayers": [ { "moveXEvents": [...], "moveYEvents": [...], "rotateEvents": [...], "alphaEvents": [...], "speedEvents": [...] } ],
  "notes": [ ... ]
}
```
* `isCover: 1`：音符越过判定线后隐藏（正常行为，保持 1）。
* `father`：父线索引（-1 无）。子线的位置是相对父线的。
* `eventLayers`：可以有多层，**同类事件各层数值相加**。第 0 层放基础值，需要叠加动画时再加第 1 层。
* 每条线的第 0 层 5 类事件都必须存在，且**第一个事件从第 0 拍开始**（Phira 对第一个事件之前的时间做外推，不从 0 开始会出现错位）。最后一个事件的值会一直保持到曲末。

### 2.3 事件
```json
{"startTime":[16,0,1], "endTime":[18,0,1], "start":-270.0, "end":-200.0, "easingType":4, "easingLeft":0.0, "easingRight":1.0, "bezier":0, "bezierPoints":[0,0,0,0], "linkgroup":0}
```
* moveX / moveY：RPE 坐标单位；rotate：角度，**正值顺时针**；alpha：0~255；speed：见 §1.3。
* 两个事件之间的空档保持前一个事件的 end 值。同一列表内事件**不要重叠**。
* easingType：1 linear, 2 outSine, 3 inSine, 4 outQuad, 5 inQuad, 6 inOutSine, 7 inOutQuad, 8 outCubic, 9 inCubic, 10 outQuart, 11 inQuart, 12 inOutCubic, 13 inOutQuart, 14 outQuint, 15 inQuint, 16 outExpo, 17 inExpo, 18 outCirc, 19 inCirc, 20 outBack, 21 inBack, 22 inOutCirc, 23 inOutBack, 24 outElastic, 25 inElastic, 26 outBounce, 27 inBounce, 28 inOutBounce, 29 inOutElastic。线条运动推荐 4/6/7/8/12（自然），20/23（回弹，点缀用）。

### 2.4 音符
```json
{"type":1, "startTime":[33,1,2], "endTime":[33,1,2], "positionX":-220.0, "above":1, "alpha":255, "isFake":0, "size":1.0, "speed":1.0, "visibleTime":999999.0, "yOffset":0.0}
```
| 字段 | 说明 |
|---|---|
| `type` | 1 Tap（点）、2 Hold（长条）、3 Flick（滑键，需甩动）、4 Drag（接，手指在即可） |
| `startTime` / `endTime` | 拍三元组；非 Hold 时两者相同；Hold 的 endTime 必须更晚 |
| `positionX` | 沿判定线的位置 |
| `above` | 1 = 从线的上方落下（常规）；0 = 从下方升上来（反向，只在特殊段落少量使用） |
| `speed` | 该音符速度倍率（默认 1，**不要随便改**，否则同一线上音符速度不一致很难读） |
| `isFake` | 1 = 假音符（不判定，纯装饰），慎用 |
| `size`/`alpha`/`yOffset`/`visibleTime` | 保持默认 |

### 2.5 多押（双押）提示
同一时刻的多个音符（任意线）会被 Phira 自动加金色描边（Double hint）。双押是"需要两只手同时按"的信号。

### 2.6 宽松写法（框架会自动规范化）
你可以只写必要字段，时间可以写小数或字符串：
```json
{"type":"tap","startTime":"33+1/2","positionX":-220}
{"type":"hold","startTime":40,"endTime":"41+1/2","positionX":150}
{"type":"drag","startTime":[41,3,4],"positionX":0}
{"type":"flick","startTime":44.5,"positionX":300}
```
`type` 可写 tap/hold/flick/drag；`startTime` 可写 `33.5`、`"33+1/2"`、`"33:1/2"`、`[33,1,2]`。其余字段自动补默认值。
**推荐流程**：每个段落写一个片段文件（如 `frags/sec2.json`，内容是音符数组），用
`phichart splice . --from 64 --to 96 --file frags/sec2.json` 写入；之后小改可以直接编辑 chart.json（`phichart fmt .` 后每个音符占一行，便于查找替换）。

---

## 3. 设计原则（采音与排键）

### 3.1 采音：有选择地跟音，不是把 onset 全打上
1. **每个段落先选"主声部"**，在 PLAN.md 写清楚：
   * 主歌/平静段：跟旋律或人声的节奏（melody），鼓只取重拍。
   * 副歌/高潮：鼓（kick + snare 骨架）+ 旋律重音，密度最高。
   * 前奏/间奏：跟最突出的乐器动机；氛围铺底用 Hold。
   * Build-up（铺垫渐强）：跟军鼓滚奏，8 分 → 16 分逐渐加密（可以用 drag 串）。
   * Breakdown / 尾奏：稀疏，长条为主。
2. **重要性层级**：小节第一拍和重音（crash / 强 kick+snare 同时）> 军鼓反拍（2、4 拍）> 主旋律节奏 > kick 的非重拍 > 次要装饰 > 踩镲（hat 几乎不单独采，最多变成 drag 串）。
3. **强度阈值**：`bars.txt` 里数字 ≥ 6 的是明显起音，优先考虑；3~5 视情况作为补充；1~2 基本忽略。碎拍连续 16 分（如 8-bit 琶音、hat 连打）**不要逐个点**，用 drag 串表现或只取其中强拍。
4. **一致性**：同一段乐句重复出现时，用相同或镜像的键型（动机），让玩家"听得出来、看得出来"。在 PLAN.md 记录动机。
5. **对比与起伏**：密度跟能量走。参考（IN 难度，平均 notes/秒）：平静 1.5~3，主歌 3~5，副歌 5~8，最高潮短时峰值 ≤ 11（1 秒窗）。EZ ×0.4，HD ×0.65，AT ×1.4。
6. **休止就留空**：音乐停顿的地方不要硬塞音符。段落之间可以留 1~2 拍呼吸。
7. **三连音**：bars.txt 行尾出现 `tri:` 或 onsets 里标 `tri` 时，用 1/3 细分，别量化成 1/4。
8. **音准时值**：每个音符必须压在真实起音上（timeline 图里音符要和左侧泳道的色块对齐）；lint 的 audio sync 应 ≥ 85%（填充性 drag 除外）。

### 3.2 音符类型怎么选
* **Tap**：清晰的打击/起音，主力（通常占 55~75%）。
* **Hold**：持续的声音（长音旋律、人声拖音、铺底和弦、贝斯长音）。长度 = 声音持续长度（看 onsets 的 `len`、频谱图的横线），起止都对齐网格，一般 ≥ 1 拍。长条结束后至少留 1/4 拍再让同一只手按下一个键。
* **Drag**：快速连续但不需要精确敲击的东西：16 分琶音、滑音、tremolo、旋律快速跑动；排成**连续的曲线/斜线**（相邻 drag 的 x 间距 ≤ 150，1/8 拍间隔时 ≤ 100），用身体"划过去"的手感。也可以在 tap 之间加 drag 当装饰音。
* **Flick**：爆发性重音（crash、乐句结尾的"甩"、刷音效、强切分）。每小节最多 1~2 个；flick 后 0.12 秒内同一位置不要再放音符；不要做 flick 连打。
* **双押**：只给真正的重音（段落首拍、crash+kick、和弦重击）。IN 难度双押约占 5~12%。两键间距 ≥ 300，通常左右对称或左右各一。

### 3.3 排键：手感与可读性
1. **双手交互**：快于 1/4 拍间隔（< ~0.3 s）的连续单键，左右交替（左手区 x<0，右手区 x>0），例如 -250/+250 或 -350/-100/+100/+350 的阶梯。
2. **禁止叠键/快速纵连**：同一位置 0.15 s 内连续两个 tap（jack）只在节奏需要强调时少量使用；绝不要在同一时间同一位置放两个音符。
3. **跳跃距离**：两个相邻单键间隔 < 0.15 s 时 x 距离不超过 ~600；大跨度只用在慢节奏处。
4. **旋律轮廓**：跟旋律时，音高高 → 偏右、低 → 偏左（或反之），整体保持在 [-500, 500]，让键型"长得像旋律"。
5. **鼓的固定映射**（建议）：kick 偏左、snare 偏右，或者 kick 中间、snare 两侧交替；一个段落内映射保持一致。
6. **Hold + Tap 组合**：一只手按长条，另一只手在另一侧点（间距 ≥ 300）；长条期间同侧不要放音符。
7. **不要交叉手**：左手区的连续键别突然跑到最右侧再回来。
8. **段落内用 2~3 种键型**（交互、阶梯、对称双押、drag 曲线、长条+点），段落之间换键型，避免全曲同一个样子。
9. **画面清爽**：渲染图里同屏音符一般不超过 ~12 个；如果画面一片乱，就是太密或流速太慢。

### 3.4 判定线表演（可选，少量即可）
* 可读性第一。默认一条水平线在 y=-270 完成整首歌完全可以。
* 可以在段落切换时做**简单**的动画：线的 y 平移（-270 ↔ -150）、小角度旋转（≤ 15°，并在有音符前转回或保持稳定）、开头 alpha 从 0 渐入、结尾渐出。
* 音符到达判定线的那一刻，线不应在快速移动/旋转（± 0.5 拍内保持静止或很慢）。
* 第二条线（如副歌左右分屏）只在你有把握时使用：两条线都要有完整的 5 类事件，坐标不要让音符出屏，并且一定用 snap 检查。
* 示例：第 64 拍用 2 拍把线从 -270 平滑抬到 -200（outQuad），同时流速 6.3→7：
```json
"moveYEvents": [
  {"startTime":[0,0,1],"endTime":[64,0,1],"start":-270,"end":-270,"easingType":1},
  {"startTime":[64,0,1],"endTime":[66,0,1],"start":-270,"end":-200,"easingType":4}
],
"speedEvents": [
  {"startTime":[0,0,1],"endTime":[64,0,1],"start":6.3,"end":6.3,"easingType":1},
  {"startTime":[64,0,1],"endTime":[65,0,1],"start":6.3,"end":7.0,"easingType":1}
]
```
（线移到 -200 后到上边缘距离变为 650，记得用 §1.3 公式重新确认可见时间。）

---

## 4. 工作流程（必须按顺序）

### 步骤 1：读分析
读 `analysis/summary.md`，看 `analysis/overview.png`，浏览 `analysis/bars.txt`。弄清：BPM、段落、哪里能量高、每段哪种声部突出、哪里有长音、有没有三连音。

### 步骤 2：验证节拍网格（在写正式音符之前）
1. 用 `phichart onsets . --from 4 --to 20 --layers kick,snare --min 0.6` 找强鼓点，在 chart.json 放 8~16 个测试 tap。
2. `phichart timeline . --from 0 --to 32` 看：测试音符是否都和泳道里的强色块在同一水平线上？强拍（每小节第 0 拍）是否真的是重音？
3. `phichart lint .` 的 audio sync 应接近 100%。
4. 如果整体偏 1/4 拍或明显错位 → `phichart analyze . --offset-ms <值> --update-chart --force`；如果小节线错位（重音落在每小节第 2 拍）→ `--downbeat-shift`；如果感觉 BPM 是一半/两倍 → `--bpm`。修好后删掉测试音符。

### 步骤 3：写 PLAN.md
表格列出每个段落：拍范围、性格、主声部、目标密度、流速 v（按 §1.3 算）、线的动作、键型/动机、刻意不采的东西。规划好再写谱。

### 步骤 4：逐段写谱（每段都执行完整的"写 → 看 → 改"循环）
对每个段落：
1. `phichart onsets . --from A --to B --layers <主声部>` 拿到候选时间点；对照 bars.txt 决定取舍。
2. 把这一段的音符写成片段 JSON，`phichart splice . --from A --to B --file frags/secN.json`（或直接编辑 chart.json）。
3. **看效果（强制）**：
   * `phichart timeline . --from A --to B` → 检查节奏是否压在起音上、密度起伏、键型形状、左右手分布。
   * `phichart snap . --around <这段最密/最复杂的拍>` → 看真实游戏画面：在击打点之前（-2、-1、-0.5 拍）屏幕上同时有哪些音符、是否重叠/遮挡、是否易读；击打点之后（+0.5、+1 拍）下一组音符是否清楚。
   * 每段至少再看 1~2 个关键位置（段落开头、双押/长条处、换速处）。
4. 修改后：`phichart snap . --around <修改处> --compare @prev`，确认 AFTER 比 BEFORE 好。修改了哪里，就要看哪里**前后**的画面。
5. `phichart lint .`，处理与本段有关的错误和警告。
6. 在 PLAN.md 的进度日志里记一行（本段完成、看过哪些图、发现并修了什么）。

### 步骤 5：流速与判定线事件
按 PLAN 写 speedEvents（以及可选的线动画）。每个换速/动画位置都 `phichart snap . --around <拍>`（看换速前后画面），并用 lint 确认可见时间。

### 步骤 6：全曲复查
1. 按 32 拍一段把全曲 timeline 都看一遍（`--from 0 --to 32`、`--from 32 --to 64`…），找：漏采的明显重音、空白太久、某段过密、键型重复单调、段落之间缺少对比。
2. `phichart lint .`：**ERRORS 必须为 0**；每条 WARNING 要么修掉，要么在 PLAN.md 写明为什么保留。
3. 抽查几个高潮点的 snap。

### 步骤 7：导出
`phichart export . --pez` → `export/chart.json`（最终交付）和 `export/chart.pez`（Phira 可直接导入）。最后用几句话总结：段落设计、音符总数/类型分布、流速设置、主要亮点。

---

## 5. 自查清单（交付前逐条确认）
- [ ] 全曲（从第一个音到最后一个音）都有谱，没有大段遗漏
- [ ] 所有音符压在真实起音上（sync ≥ 85%），三连音用了 1/3
- [ ] 采音有取舍：主声部清晰，没有逐个点碎音
- [ ] 密度跟随能量起伏，高潮最密，平静段明显稀疏
- [ ] 同时音符 ≤ 2（包括正在按住的长条），双押间距 ≥ 300
- [ ] 没有重叠、没有出屏、没有手交叉、没有离谱的快速大跳
- [ ] Hold 对应持续音，Flick 只在爆发点，Drag 串成顺滑曲线
- [ ] 可见时间在 0.6~1.3 s，段落内流速恒定
- [ ] 线条事件都从第 0 拍开始，击打时线是稳定的
- [ ] lint 0 错误；已导出 export/chart.json

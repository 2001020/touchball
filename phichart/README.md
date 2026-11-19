# phichart — 让单个模型为 Phira 制作自制谱

传入一个音频文件，框架完成音频分析，然后由**一个模型**独立完成分段 / 采音设计、编写 **RPE JSON** 谱面（Phira 原生支持的自制谱格式），
并在每次创作或修改后用 **Phira 本身的渲染引擎**（TeamFlos/phira 的 `prpr` crate）把指定拍渲染成图片自查，最终交付 json（另附可直接导入 Phira 的 `.pez`）。

```
audio ──► phichart init ──► analysis/ (BPM·offset·分段·5声部onset表·频谱总览)
                │
                ▼
      模型（Claude Code 无头模式 / Messages API / 任意 agent）
        读 GUIDE.md → 写 PLAN.md → 逐段写 chart.json
        ↺ phichart timeline / snap(真引擎渲染) / lint → 看图 → 修改
                │
                ▼
      phichart export ──► export/chart.json（最终交付）+ chart.pez
```

## 安装

```bash
bash scripts/setup.sh
```

脚本会：安装系统依赖（ffmpeg、Xvfb、GL/ALSA 开发库）、`pip install -e .`、克隆 Phira 源码到 `third_party/phira`（固定到测试过的提交），
把 `engine/phira-snap`（基于 prpr 的无头逐帧渲染器，约 200 行 Rust，不修改 Phira 任何代码）拷进 Phira 工作区并编译。
渲染在虚拟显示（Xvfb + Mesa）上进行，音频输出到 ALSA null 设备，因此服务器 / 容器里也能跑。

## 一条命令出谱

```bash
phichart make song.mp3 --out work/song --level "IN Lv.12"          # 默认 backend: claude-code
phichart make song.mp3 --out work/song --backend api                # Anthropic Messages API（需 pip install anthropic 和凭证）
phichart make song.mp3 --out work/song --backend manual             # 只准备工作区并打印任务提示，交给你自己的 agent
```

结束后：`work/song/export/chart.json`（严格 RPE，交付物）、`export/chart.pez`（导入 Phira）、`PLAN.md`（模型的规划与自查日志）。

## 给模型用的工具（CLI）

| 命令 | 作用 |
|---|---|
| `phichart init audio --out W` | 转码、分析、生成谱面骨架、拷贝 GUIDE.md、PLAN.md 模板 |
| `phichart analyze W [--bpm --offset-ms --downbeat-shift --update-chart]` | 重新分析 / 修正网格 |
| `phichart onsets W --from A --to B [--layers ..] [--rank K]` | 起音列表；`--rank` 给出每小节最突出的 K 个候选位置（有选择地采音） |
| `phichart snap W --around B [--compare @prev]` | **Phira 真引擎**渲染 B 拍前后的画面（拼图 + 拍号/时间标签 + x 标尺）；`--compare` 上下对比修改前后 |
| `phichart timeline W --from A --to B` | 编辑器式总览：音符 vs 5 条 onset 泳道 |
| `phichart lint W` | 多押手数、重叠、出屏、叠键、快速大跳、密度、可见时间（流速）、音频同步率、空白小节 |
| `phichart splice W --from A --to B --file frag.json` | 用片段替换一段音符（自动存档） |
| `phichart checkpoint / history / notes / fmt / stats` | 存档、列表、格式化等 |
| `phichart export W --pez` | 导出最终 json / pez |
| `phichart video W` | 渲染带音乐和打击音的预览 mp4（给人看的） |

模型的全部规则写在 [`GUIDE.md`](GUIDE.md)：RPE 格式细节（拍三元组、坐标系、事件层相加、easing 表、宽松写法）、
由 Phira 源码推导的关键数字（音符宽 ≈178 单位、`可见时间 = (450−lineY)/(120.2×v)` 的流速表）、
采音原则（每段选主声部、重要性层级、强度阈值、动机一致、密度随能量起伏、留白、三连音）、
音符类型选择、排键手感规则（双手交互、禁止叠键/交叉手、长条+点的分手、双押间距…）、判定线表演的克制原则，
以及**强制的"写 → 渲染看前后 → 改"循环**和交付前自查清单。

## 实现要点

* **格式与引擎来源**：直接读 Phira 的 `prpr/src/parse/rpe.rs`、`core/{line,note,anim,tween}.rs` 得到语义（速度积分、`SPEED_RATIO`、音符宽度、事件层相加、第一个事件前外推、负 offset 的处理等），lint / 可见时间计算按同样的数学实现；画面则直接由 prpr 渲染，所见即游戏所得。
* **音频分析**（librosa）：HPSS 分出打击/和声，5 个频段的 onset 强度做中值去底的显著性后峰值检测；BPM 用网格搜索（相位 × BPM 最大化拍点/八分点能量，并偏好整数 BPM），再用强 onset 的中位偏差校正相位；小节线按低频重音选取；第 0 拍放在第一个强拍前一小节作引导（offset 可为负，Phira 会提前开始计时）；自相似矩阵 checkerboard novelty + 能量跳变做分段并按相似度打 A/B/C 标签；沿主音高频带跟踪延音长度，给出 Hold 候选。
* **后端**：`claude-code` 用 `claude -p` 无头运行，只放行 Read/Write/Edit/Glob/Grep 与 `phichart` 命令；`api` 是手写的工具循环（流式 + 自适应思考 + 服务端压缩 + 拒答回退，工具：phichart/read/write/edit/view_image/finish，带输入校验与工作区路径限制）。

## 示例

`examples/itty_bitty/`：用 Kevin MacLeod《Itty Bitty 8 Bit》前 97 秒（incompetech.com，CC BY 4.0）按 GUIDE 流程完成的谱面，
含最终 `chart.json`、`PLAN.md`（规划与审阅日志）、各段片段文件和若干渲染图。音频不随仓库分发。

`examples/polka_autonomous/`：**完全无人干预**的端到端运行结果——
`phichart make polka_cut.mp3 --out work/polka`（Kevin MacLeod《Pixel Peeker Polka - faster》前 36 秒，CC BY 4.0），
后端为 Claude Code 无头模式：45 轮工具调用，16 次查看渲染图（timeline / 真引擎 snap / --compare），
产出 144 个音符，lint 0 错误 0 警告，同步率 100%，花费约 1.5 美元。`PLAN.md` 是模型自己写的规划与审阅日志，`make_console.log` 是控制台记录。

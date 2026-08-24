# 会话交接：BTC 先导性研究（转本地续做）

> 用途：把云端会话的完整上下文交接给本地 Claude Code 会话。
> 分支 `claude/btc-hype-lit-sol-alpha-4f9kf1`，最新提交 `3c6270f`。

## 一、原始问题

以 BTC 为先导指标买入 HYPE、LIT、SOL，是否存在价格反应上的**时间差（lead-lag）**？是否有 **Alpha**？

其中 **LIT = Lighter**（zk-rollup 永续 DEX，2025-12-30 TGE + 25% 空投），**不是** Litentry。

## 二、最终结论

### 主结论（613 天全样本，2024-12-15 → 2026-08-23）

**日频不存在可利用的时间差，追涨与抄底两个方向都没有 Alpha。**

| 指标 | HYPE | SOL |
|---|---|---|
| 同日相关 | 0.51 | 0.78 |
| **lag+1 相关** | **−0.000** | −0.07 |
| Granger btc→alt p (lag1) | 0.97 | 0.06 |
| 控制 btc[t+1] 后 btc[t] 的 t 值 | 0.21 | −0.56 |

- 六条 BTC 信号规则**没有一条**毛收益追上买入持有（HYPE B&H +1.45，最好规则 +0.72），全部 Alpha 的 t 值在 ±1.1 内。
- 事件研究：BTC ±3% 之后，次日起两个方向都归零。
- 周频 lag+1 全不显著；2020-21 年确实存在的 2-3 日 / 1-2 周传导，2024-26 已消失。
- SOL/ETH 提供**不对称 Beta**（下行 1.39/1.37 vs 上行 1.06/1.11，口径稳健）。HYPE **不在此列**。
- HYPE/LIT 由自身叙事主导：BTC 只解释 HYPE 方差的 ~26%（60 日相关 0.33-0.73，现值 0.52）。
- 真正的领先只在分钟级，属于高频套利，日线测不到。

### 三处对初版报告的修正（重要）

| 原报告 | 修正后 | 原因 |
|---|---|---|
| BTC 大跌后 HYPE 反弹 +2.5% (t=2.5) | **不成立**：+0.5% (t=0.4) | 主因是**口径**：换一个同样合理的 BTC 价格源，同一时期即掉到 t=0.91（事件日 45→37 天） |
| HYPE 下行 β > 上行 β | **无一致不对称**（翻转为 1.13/0.91） | 随数据源翻转 |
| Granger lag1 p=0.049 | **p=0.97** | 口径 + 样本外数据 |

方法论要点：**口径一换就消失的效应不是真信号。**

### 采样假象（差点被骗的一次）

只看 2026-05-24..08-23（n=92）会看到与主结论相反的信号：lag+1 +0.29 (t=2.7)、Granger p=0.006、回测 Sharpe 3.9、年化 Alpha +193%。**这是数据采样产物**，五项诊断：

1. 同源的 SOL(+0.39)/ETH(+0.36) 出现更强的同一现象（时间戳绝对一致，排除跨源错位）
2. 该窗口 BTC 自身 ρ(1)=**+0.425**，而同源此前 809 天为 −0.091、独立源 −0.058
3. 三个币的 lag+1 全部 ≈ ρ_btc(1) × 同期相关（机械传导）
4. 控制 btc[t+1] 后，SOL(t=−1.4)、HYPE(t=+0.7) 均不显著
5. VR(2)=1.43（此前 0.91）→ npm 快照抓取时点近三个月漂移

脚本已内置 `sampling_quality`(ρ(1)、VR(2)) 与 `lag1_mechanical_benchmark`(ρ×corr0) 自动诊断。

## 三、数据管道（关键坑）

| 面板 | 来源 | 覆盖 | 时间戳约定 |
|---|---|---|---|
| CM | coinmetrics/data GitHub 镜像 | BTC/ETH PriceUSD 全史；SOL/HYPE 用 CapMrktEstUSD 反推 → 2026-05-23 | 行 D = CM 的 ReferenceRate**[D+1]** |
| API | npm `@fawazahmed0/currency-api` 每日快照 904 版 | BTC/ETH/SOL → 2026-08-23 | ~00:00 UTC，行 D = ReferenceRate[D] |
| HYPE 补全 | CoinGecko（用户本地跑 `fetch_hype_extension.py`） | 2026-02-25 → 08-23（181 天） | 同 API 网格 |

**踩过的坑，务必记住：**

1. **CM 社区 CSV 有内部错位**：`CapMrktEstUSD[D]` 用的是 `ReferenceRateUSD[D+1]` 的价格（实测比值恒为 238.4M），BTC 的 `PriceUSD[D]` 同样如此。**两条腿错位方向一致**，所以原 CM 配对本身没错；但并入 API 网格需整体前移一天。
2. **配对必须同网格**：补全数据 `ext[D] ↔ api_btc[D]` 同日相关 +0.51，错配成 `api_btc[D+1]` 则为 **−0.23**——配错腿会凭空造出一天的领先。
3. **拼接点** 2026-02-26，重叠 87 天相关 **0.994**。
4. **CoinGecko 日线末尾有重复日期**（追加的当前快照），脚本已 `drop_duplicates(keep='first')`。
5. **HYPE 有 1 个流通量修订日**（2025-08-28）已标记剔除；API 面板 2025-12-06 快照损坏已剔除。
6. **web 检索的价格锚点不可靠**：真实日线到位后校对，误差最大 +14.8%（2026-06-16 锚点 $76.77，实际 $66.89）。已全部弃用。
7. 云端沙箱出口网络白名单制，40+ 行情端点全被 403；Coin Metrics GitHub 仓库只是镜像，正主是 GitLab 私有库 `coinmetrics/data-delivery/data`，镜像同步 2026-05-24 后中断。**本地无此限制。**

## 四、文件结构

```
analysis/btc_leadlag/
├── README.md                    # 完整中文研究报告（含 §0 修正、§4.2 采样假象）
├── HANDOFF.md                   # 本文件
├── build_dataset.py             # 从两个源构建面板（含数据工程记录）
├── fetch_hype_extension.py      # 抓 HYPE 日线补全（仅标准库，需普通网络）
├── btc_leadlag_analysis.py      # 全部统计 → results.json
├── make_figures.py              # 四张图 → figures/
├── results.json                 # 所有配对的完整结果
├── data/
│   ├── daily_panel_cm.csv       # CM 面板
│   ├── daily_panel_api.csv      # npm 快照面板
│   ├── hype_daily_extension.csv # 补全的 HYPE 日线（181 天）
│   ├── lit_lighter_cm.csv       # LIT 仅 7 个日度价格
│   └── *_anchor_points.csv      # 稀疏锚点（LIT 仍在用，HYPE 的已弃用仅留追溯）
└── figures/fig1..fig4*.png
```

`results.json` 里的配对：`HYPE_vs_BTC_full`（主）、`HYPE_vs_BTC_cm`（原口径）、`HYPE_vs_BTC_gap_only`（假象窗口）、`SOL_vs_BTC_api`、`SOL_vs_BTC_cm_long`、`ETH_vs_BTC_api`、`LIT_lighter`。

## 五、本地重跑

```bash
git checkout claude/btc-hype-lit-sol-alpha-4f9kf1
cd analysis/btc_leadlag
pip install pandas numpy statsmodels matplotlib
python btc_leadlag_analysis.py    # → results.json
python make_figures.py            # → figures/
python fetch_hype_extension.py    # 需要更新 HYPE 日线时再跑
```

## 六、未做 / 可续做

1. **LIT 仍是空白**：只有 7 个日度价格，无法做任何统计。本地跑一个 Lighter 版的 extension 抓取（CoinGecko id `lighter`）就能补上完整分析。
2. **BTC 腿的数据质量**：npm 快照近三个月有采样漂移。本地可用交易所 K 线（Binance/Coinbase）重建 BTC/SOL/ETH 面板，消除该噪声后重跑——预期结论不变但统计更干净。
3. **分钟级检验**：日线无法验证真正的领先。有分钟数据的话可以测 1-60 分钟尺度的 lead-lag 和衰减速度。
4. **未开 PR**：分支已推送但**没有创建 PR**（用户未要求）。

## 七、产出链接

- 报告网页（Artifact）：https://claude.ai/code/artifact/72727ba7-bb19-4460-b35a-35b068fa2e2f
- 分支：`claude/btc-hype-lit-sol-alpha-4f9kf1`

**免责**：本研究为历史统计描述，不构成投资建议。

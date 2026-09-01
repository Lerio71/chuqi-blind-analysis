# 楚奇网英超盲测复盘系统

基于楚奇网（chuqi.com）数据的英超赛季盲测分析与复盘系统。

## 核心功能

1. **数据采集**：从楚奇网抓取欧赔（20家）、亚盘（17家）、必发数据
2. **盲测分析**：屏蔽赛果，按 v15 信号体系自动判定五项预测
3. **赛后复盘**：揭晓赛果后逐项对照、归因、提取经验
4. **经验迭代**：每场复盘自动沉淀新规律，经验库持续增长

## 项目结构

```
chuqi-blind-analysis/
├── scraper/
│   ├── chuqi_lib.py            # 核心抓取库（HTTP并发+JSON提取+欧赔/亚盘/必发解析）
│   ├── chuqi_pipeline.py       # 一键管道（单场/批量提取→structured.json）
│   ├── blind_read.py           # 盲测读取（屏蔽赛果+信号检测）
│   ├── analyze_signals.py      # v15信号引擎（6级优先级+66条经验规则）
│   └── generate_review.py      # 赛后复盘（对照+归因+经验提取+报告）
├── .github/workflows/
│   ├── blind-analyze.yml       # 赛前盲测分析（03:00 + 03:45）
│   └── post-review.yml         # 赛后复盘（06:00）
├── match_data/                 # 比赛数据（structured.json + prediction.json）
│   ├── season_data.json        # 赛季列表
│   ├── match_scores.json       # 赛果
│   └── reviews/                # 复盘报告
├── data/                       # 分析报告 + 经验库
├── requirements.txt
└── README.md
```

## v15 信号优先级

1. **轮次豪门回调风险** + **轮次主客倾向**（上位变量）
2. **主队大热冷热<1 + 对手弱旅 = 主胜**（#2/47/48）
3. **客队大热冷热极低 + 客队非客场强主 = 客胜**（#3/31）
4. **主队大热 + 盘赔反向 = 防冷**（#63）
5. **盘赔反向 + 主队50% + 主场 = 主胜回归**（#66）
6. **主队大热冷热>1 = 防平**（#65）

## 核心规律（100场全量验证）

| 规律 | 数据 | 经验号 |
|------|------|--------|
| 主队大热(65%+)主胜率 | 67% | #48 |
| 客队大热(55%+)客胜率 | 仅43% | #47 |
| 盘赔反向→主队不胜率 | 55% | #49 |
| 盘赔同向→主胜率 | 仅38%（诱上） | #50 |
| 深盘大热赢盘率 | 仅47% | #51 |

## 本地使用

```bash
pip install -r requirements.txt

# 更新赛季数据
cd scraper
python chuqi_pipeline.py --season

# 单场提取
python chuqi_pipeline.py 14586460

# 盲测分析
python blind_read.py 14586460

# 赛后复盘
python generate_review.py 14586460

# 批量复盘
python generate_review.py --batch ids.txt

# 今日全部复盘
python generate_review.py --today
```

## GitHub Actions 时间表

| 工作流 | 北京时间 | 说明 |
|--------|---------|------|
| 赛前盲测 | 03:00, 03:45 | 抓取数据→屏蔽赛果→v15信号分析→生成prediction.json |
| 赛后复盘 | 06:00 | 提取赛果→逐项对照→归因→经验提取→更新经验库 |

## 自动化流程

```
03:00 赛前 ─→ 抓取完整数据（欧赔+亚盘+必发）
           ─→ 盲测读取（屏蔽赛果）
           ─→ v15信号分析 → prediction.json
           ─→ commit to GitHub

06:00 赛后 ─→ 从赛季列表提取赛果
           ─→ 逐项对照预测 vs 实际
           ─→ 归因分析
           ─→ 提取新经验 → 经验库
           ─→ daily_review.json
```

# XLBCalendar

一个把 LPL 赛程自动整理成日历文件的工具。

## 它做什么

- 从腾讯 LPL 接口拉取比赛数据
- 把多个接口返回的原始 JSON 保存到 `raw/` 目录
- 再统一读取并合并这些 JSON 数据
- 生成标准的 `.ics` 日历文件
- 输出两个日历：
  - `LPL赛程.ics`：全部赛程
  - `BLG赛程.ics`：只包含 BLG 的赛程
- 生成完成后可直接导入系统日历、Apple 日历、Google 日历等支持 ICS 的应用

## 文件说明

- `LPL_T.py`
  - 拉取多个 LPL 接口数据
  - 保存原始 JSON 到 `raw/json1.json`、`raw/json2.json`
  - 解析比赛结果
  - 按赛段统计胜负关系
  - 输出控制台日志

- `convert_to_ics.py`
  - 读取 `raw/` 下的多个 JSON 文件
  - 合并后再转换成 `.ics` 文件
  - 转换成 `.ics` 文件
  - 生成全量赛程和 BLG 赛程两个日历

- `auto_lpl.sh`
  - 一键执行数据拉取、日历生成、git 提交和推送

- `.gitignore`
  - 忽略缓存文件和中间产物

## 运行方式

先确保你本机有 Python 环境，并且能使用 `python3` 命令。

然后在项目目录执行：

```bash
bash auto_lpl.sh
```

也可以分步执行：

```bash
python3 LPL_T.py
python3 convert_to_ics.py
```

## 输出文件

脚本运行后会生成或更新以下文件：

- `raw/json1.json`
- `raw/json2.json`
- `json.json`
- `LPL赛程.ics`
- `BLG赛程.ics`

## 逻辑说明

- `LPL_T.py` 里只统计 `MatchStatus == "3"` 的比赛，也就是已经结束的比赛
- `convert_to_ics.py` 会先合并 `raw/` 下的 JSON，并按 `MatchDate` 排序，再把每场比赛写成一个日历事件
- `UID` 使用 `bMatchId` 生成，方便日历应用识别同一场比赛并更新事件
- `SEQUENCE` 用来区分未开始和已结束比赛
- 日历标题前缀会根据 `GameName` / `GameTypeName` 自动映射，例如 `LPL`、`FST`、`MSI`
- 如果 `TeamShortNameA` / `TeamShortNameB` 缺失，会尝试从 `bMatchName` 中按 `vs` 解析队伍名
- 拓扑结构输出也会带同样的赛事前缀，方便区分不同赛事来源

## 注意事项

- 如果接口字段名变化，脚本可能需要同步调整
- 每次下载前，`raw/` 会被清空，确保只保留本次抓取的数据
- `raw/` 里的 JSON 是中间产物，默认不会提交到仓库
- `json.json` 现在是合并后的中间产物，默认不会提交到仓库

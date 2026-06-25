#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 LPL 赛程 JSON 转换为 iCalendar (.ics) 格式

UID 设计规则：
- 使用 bMatchId 作为唯一标识符
- 格式：lpl-match-{bMatchId}@lpl.schedule
- 确保同一场比赛的 UID 始终相同，支持日历应用更新事件而非创建重复

更新机制：
- 当比赛结束后，再次执行脚本会更新已有日程
- 通过 SEQUENCE 字段标识版本（未开始=0，已结束=1）
- 日历应用会自动识别并更新同 UID 的事件
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
GAME_PREFIX_RULES = [
    ("职业联赛", "LPL"),
    ("全球先锋赛", "FST"),
    ("季中冠军赛", "MSI"),
]

def parse_score(value):
    """把比分字段尽量转成整数，失败时返回 None"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None

def parse_datetime(date_str):
    """解析日期时间字符串，返回 datetime 对象"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except:
        return None

def get_field(match, *names, default=""):
    """按多个字段名依次取值，兼容大小写和不同来源字段"""
    for name in names:
        if name in match and match.get(name):
            return match.get(name)
        lower_name = name.lower()
        if lower_name in match and match.get(lower_name):
            return match.get(lower_name)
    return default

def get_game_prefix(match):
    """根据 GameName / GameTypeName 映射赛事前缀"""
    game_name = str(get_field(match, "GameName", "GameTypeName", default=""))
    for keyword, prefix in GAME_PREFIX_RULES:
        if keyword in game_name:
            return prefix
    return "LPL"

def parse_teams(match):
    """优先读取队伍简称，缺失时从 bMatchName 兜底解析"""
    team_a = str(get_field(match, "TeamShortNameA", default="")).strip()
    team_b = str(get_field(match, "TeamShortNameB", default="")).strip()

    if team_a and team_b:
        return team_a, team_b

    match_name = str(get_field(match, "bMatchName", default=""))
    if "vs" in match_name:
        left, right = match_name.split("vs", 1)
        left = left.strip()
        right = right.strip()
        if not team_a:
            team_a = left
        if not team_b:
            team_b = right

    # 如果解析出来的team_a == team_b 直接返回默认值
    if team_a == team_b:
        team_a = "TBDA"
        team_b = "TBDB"
    return team_a or "TBDA", team_b or "TBDB"

def format_ics_datetime(dt):
    """将 datetime 转换为 iCalendar 格式 (本地时间)"""
    return dt.strftime("%Y%m%dT%H%M%S")

def escape_ics_text(text):
    """转义 iCalendar 文本中的特殊字符"""
    text = str(text)
    text = text.replace('\\', '\\\\')
    text = text.replace(',', '\\,')
    text = text.replace(';', '\\;')
    text = text.replace('\n', '\\n')
    return text

def unescape_ics_text(text):
    """还原 iCalendar 文本中的转义字符"""
    text = str(text)
    text = text.replace('\\n', '\n')
    text = text.replace('\\;', ';')
    text = text.replace('\\,', ',')
    text = text.replace('\\\\', '\\')
    return text

def unfold_ics_lines(raw_text):
    """把折行的 ICS 行恢复成完整行"""
    lines = raw_text.splitlines()
    unfolded = []
    for line in lines:
        if line.startswith((' ', '\t')) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded

def parse_existing_events(ics_path):
    """读取已有 ICS 文件，按 UID 保存上一版事件的关键信息"""
    path = Path(ics_path)
    if not path.exists():
        return {}

    try:
        raw_text = path.read_text(encoding='utf-8')
    except Exception:
        return {}

    events = {}
    current = None

    for line in unfold_ics_lines(raw_text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("UID"):
                events[current["UID"]] = current
            current = None
            continue

        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()

        if key in {"UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "DESCRIPTION", "LOCATION", "STATUS", "SEQUENCE"}:
            current[key] = unescape_ics_text(value)

    return events

def load_merged_json_data(raw_dir):
    """读取 raw 目录下所有 json*.json 并合并成一个数据集"""
    merged_matches = []
    seen_match_ids = set()

    if not raw_dir.exists():
        return {"msg": []}

    for json_path in sorted(raw_dir.glob("json*.json")):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ 跳过损坏文件 {json_path.name}: {e}")
            continue

        for match in data.get("msg", []):
            match_id = match.get("bMatchId")
            if match_id in seen_match_ids:
                continue
            seen_match_ids.add(match_id)
            merged_matches.append(match)

    merged_matches.sort(key=lambda match: (
        parse_datetime(match.get("MatchDate", "")) or datetime.max,
        str(match.get("bMatchId", "")),
    ))

    return {"msg": merged_matches}

def generate_uid(match):
    """为每场比赛生成唯一 UID

    使用 bMatchId 作为唯一标识，确保同一场比赛的 UID 始终相同
    这样日历应用会识别为同一事件并更新，而不是创建重复事件
    """
    match_id = match.get('bMatchId', '')
    return f"lpl-match-{match_id}@lpl.schedule"

def create_ics_event(match):
    """为单场比赛创建 iCalendar 事件"""
    # 解析比赛时间
    match_date = parse_datetime(match.get('MatchDate', ''))
    if not match_date:
        return None

    # 比赛状态：1=未开始，2=进行中，3=已结束
    match_status = match.get('MatchStatus', '1')

    # 跳过状态为1（未开始）且没有具体时间的比赛
    if match_status == '1' and match.get('ScoreA') == '0' and match.get('ScoreB') == '0':
        # 这些是未来的比赛，保留
        pass

    # 估算比赛时长（BO3约2小时，BO5约3小时）
    game_mode = match.get('GameModeName', 'BO3')
    duration = timedelta(hours=3) if game_mode == 'BO5' else timedelta(hours=2)
    match_end = match_date + duration

    # 构建比赛标题 - 格式：LPL: TES vs WE 17:00
    team_a, team_b = parse_teams(match)
    match_time = match_date.strftime("%H:%M")
    summary = f"{get_game_prefix(match)}: {team_a} vs {team_b} {match_time}"

    # 构建比赛描述
    description_parts = []
    description_parts.append(f"{match.get('bMatchName', '')}")
    description_parts.append(f"{game_mode}")
    description_parts.append(f"{match.get('GameTypeName', '')}")

    if match_status == '3':  # 已结束
        score_a_raw = match.get('ScoreA', '0')
        score_b_raw = match.get('ScoreB', '0')
        score_a = parse_score(score_a_raw)
        score_b = parse_score(score_b_raw)
        winner = team_a if match.get('MatchWin') == '1' else team_b
        description_parts.append(winner)
        if score_a is not None and score_b is not None:
            if score_a > score_b:
                description_parts.append(f"{score_a} - {score_b}")
            else:
                description_parts.append(f"{score_b} - {score_a}")
        else:
            description_parts.append(f"{score_a_raw} - {score_b_raw}")


    description = escape_ics_text(' '.join(description_parts))

    # 比赛地点
    location = escape_ics_text(match.get('GamePlaceName', ''))

    # 生成事件
    event = []
    event.append("BEGIN:VEVENT")
    event.append(f"UID:{generate_uid(match)}")
    event.append(f"DTSTAMP:{format_ics_datetime(datetime.now())}")
    event.append(f"DTSTART:{format_ics_datetime(match_date)}")
    event.append(f"DTEND:{format_ics_datetime(match_end)}")
    event.append(f"SUMMARY:{escape_ics_text(summary)}")
    event.append(f"DESCRIPTION:{description}")
    event.append(f"LOCATION:{location}")

    # 如果比赛已结束，标记为已确认；添加 SEQUENCE 用于版本控制
    if match_status == '3':
        event.append("STATUS:CONFIRMED")
        event.append("SEQUENCE:1")  # 已结束的比赛，版本号为1
    else:
        event.append("STATUS:TENTATIVE")
        event.append("SEQUENCE:0")  # 未开始的比赛，版本号为0

    event.append("END:VEVENT")

    return '\n'.join(event)

def create_ics_event_with_history(match, previous_event=None):
    """结合上一版事件信息生成 iCalendar 事件"""
    match_date = parse_datetime(match.get('MatchDate', ''))
    if not match_date:
        return None

    match_status = match.get('MatchStatus', '1')
    game_mode = match.get('GameModeName', 'BO3')
    duration = timedelta(hours=3) if game_mode == 'BO5' else timedelta(hours=2)
    match_end = match_date + duration

    team_a, team_b = parse_teams(match)
    match_time = match_date.strftime("%H:%M")
    summary = f"{get_game_prefix(match)}: {team_a} vs {team_b} {match_time}"

    description_parts = [
        f"{match.get('bMatchName', '')}",
        f"{game_mode}",
        f"{match.get('GameTypeName', '')}",
    ]

    if match_status == '3':
        score_a_raw = match.get('ScoreA', '0')
        score_b_raw = match.get('ScoreB', '0')
        score_a = parse_score(score_a_raw)
        score_b = parse_score(score_b_raw)
        winner = team_a if match.get('MatchWin') == '1' else team_b
        description_parts.append(winner)
        if score_a is not None and score_b is not None:
            if score_a > score_b:
                description_parts.append(f"{score_a} - {score_b}")
            else:
                description_parts.append(f"{score_b} - {score_a}")
        else:
            description_parts.append(f"{score_a_raw} - {score_b_raw}")

    description = escape_ics_text(' '.join(description_parts))
    location = escape_ics_text(match.get('GamePlaceName', ''))

    uid = generate_uid(match)
    existing_stamp = previous_event.get("DTSTAMP") if previous_event else None
    existing_sequence = previous_event.get("SEQUENCE") if previous_event else None

    current_signature = {
        "DTSTART": format_ics_datetime(match_date),
        "DTEND": format_ics_datetime(match_end),
        "SUMMARY": escape_ics_text(summary),
        "DESCRIPTION": description,
        "LOCATION": location,
        "STATUS": "CONFIRMED" if match_status == '3' else "TENTATIVE",
    }

    previous_signature = None
    if previous_event:
        previous_signature = {
            "DTSTART": previous_event.get("DTSTART", ""),
            "DTEND": previous_event.get("DTEND", ""),
            "SUMMARY": previous_event.get("SUMMARY", ""),
            "DESCRIPTION": previous_event.get("DESCRIPTION", ""),
            "LOCATION": previous_event.get("LOCATION", ""),
            "STATUS": previous_event.get("STATUS", ""),
        }

    is_unchanged = previous_signature == current_signature

    if is_unchanged and existing_stamp:
        dtstamp = existing_stamp
    else:
        dtstamp = format_ics_datetime(datetime.now())

    if is_unchanged and existing_sequence is not None:
        sequence = existing_sequence
    elif previous_sequence := (previous_event.get("SEQUENCE") if previous_event else None):
        try:
            sequence = str(int(previous_sequence) + 1)
        except (TypeError, ValueError):
            sequence = "1" if match_status == '3' else "0"
    else:
        sequence = "1" if match_status == '3' else "0"

    event = []
    event.append("BEGIN:VEVENT")
    event.append(f"UID:{uid}")
    event.append(f"DTSTAMP:{dtstamp}")
    event.append(f"DTSTART:{format_ics_datetime(match_date)}")
    event.append(f"DTEND:{format_ics_datetime(match_end)}")
    event.append(f"SUMMARY:{escape_ics_text(summary)}")
    event.append(f"DESCRIPTION:{description}")
    event.append(f"LOCATION:{location}")
    event.append(f"STATUS:{current_signature['STATUS']}")
    event.append(f"SEQUENCE:{sequence}")
    event.append("END:VEVENT")

    return '\n'.join(event)

def convert_json_to_ics(json_file, ics_file, team_filter=None, calendar_name=None):
    """将 JSON 文件转换为 ICS 文件

    Args:
        json_file: JSON 源文件路径
        ics_file: 输出的 ICS 文件路径
        team_filter: 可选，队伍名称过滤（如 "BLG"），只包含该队伍的比赛
        calendar_name: 可选，日历名称，默认为 "LPL 赛程"
    """
    # 读取 JSON 文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    previous_events = parse_existing_events(ics_file)

    # 设置日历名称和描述
    if calendar_name is None:
        calendar_name = "LPL 赛程"
        calendar_desc = "英雄联盟LPL职业联赛 & 世界赛赛程"
    else:
        calendar_desc = f"英雄联盟LPL职业联赛 & 世界赛赛程 {calendar_name}"

    # 开始构建 ICS 文件
    ics_content = []
    ics_content.append("BEGIN:VCALENDAR")
    ics_content.append("VERSION:2.0")
    ics_content.append("PRODID:-//LPL Schedule//CN")
    ics_content.append("CALSCALE:GREGORIAN")
    ics_content.append("METHOD:PUBLISH")
    ics_content.append(f"X-WR-CALNAME:{calendar_name}")
    ics_content.append("X-WR-TIMEZONE:Asia/Shanghai")
    ics_content.append(f"X-WR-CALDESC:{calendar_desc}")

    # 处理每场比赛
    matches = data.get('msg', [])
    event_count = 0

    for match in matches:
        # 如果设置了队伍过滤，检查是否包含该队伍
        if team_filter:
            team_a = match.get('TeamShortNameA', '')
            team_b = match.get('TeamShortNameB', '')
            if team_filter.upper() not in [team_a.upper(), team_b.upper()]:
                continue

        event = create_ics_event_with_history(match, previous_events.get(generate_uid(match)))
        if event:
            ics_content.append(event)
            event_count += 1

    ics_content.append("END:VCALENDAR")

    # 写入 ICS 文件
    with open(ics_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ics_content))

    return event_count

if __name__ == "__main__":
    try:
        data = load_merged_json_data(RAW_DIR)
        json_file = BASE_DIR / "json.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        # 生成全部赛程
        ics_file_all = BASE_DIR / "LPL赛程.ics"
        count_all = convert_json_to_ics(json_file, ics_file_all)
        print(f"✓ 成功转换全部赛程 {count_all} 场比赛")
        print(f"✓ 已保存到: {ics_file_all}")

        # 生成 BLG 队伍赛程
        ics_file_blg = BASE_DIR / "BLG赛程.ics"
        count_blg = convert_json_to_ics(
            json_file,
            ics_file_blg,
            team_filter="BLG",
            calendar_name="LPL BLG 赛程"
        )
        print(f"✓ 成功转换 BLG 赛程 {count_blg} 场比赛")
        print(f"✓ 已保存到: {ics_file_blg}")

    except Exception as e:
        print(f"✗ 转换失败: {e}")
        import traceback
        traceback.print_exc()

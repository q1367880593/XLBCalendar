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
    team_a = match.get('TeamShortNameA', '')
    team_b = match.get('TeamShortNameB', '')
    match_time = match_date.strftime("%H:%M")
    summary = f"LPL: {team_a} vs {team_b} {match_time}"

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

def convert_json_to_ics(json_file, ics_file, team_filter=None, calendar_name=None):
    """将 JSON 文件转换为 ICS 文件

    Args:
        json_file: JSON 源文件路径
        ics_file: 输出的 ICS 文件路径
        team_filter: 可选，队伍名称过滤（如 "BLG"），只包含该队伍的比赛
        calendar_name: 可选，日历名称，默认为 "LPL 2026 赛程"
    """
    # 读取 JSON 文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 设置日历名称和描述
    if calendar_name is None:
        calendar_name = "LPL 2026 赛程"
        calendar_desc = "英雄联盟职业联赛 2026 赛季赛程"
    else:
        calendar_desc = f"英雄联盟职业联赛 2026 赛季 {calendar_name}"

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

        event = create_ics_event(match)
        if event:
            ics_content.append(event)
            event_count += 1

    ics_content.append("END:VCALENDAR")

    # 写入 ICS 文件
    with open(ics_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ics_content))

    return event_count

if __name__ == "__main__":
    json_file = BASE_DIR / "json.json"

    try:
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
            calendar_name="LPL 2026 BLG 赛程"
        )
        print(f"✓ 成功转换 BLG 赛程 {count_blg} 场比赛")
        print(f"✓ 已保存到: {ics_file_blg}")

    except Exception as e:
        print(f"✗ 转换失败: {e}")
        import traceback
        traceback.print_exc()

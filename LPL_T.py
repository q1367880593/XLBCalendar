import requests
import json
import networkx as nx
from pathlib import Path
import shutil

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
MATCH_LIST_URLS = [
    "https://lpl.qq.com/web201612/data/LOL_MATCH2_MATCH_HOMEPAGE_BMATCH_LIST_237.js",
    "https://lpl.qq.com/web201612/data/LOL_MATCH2_MATCH_HOMEPAGE_BMATCH_LIST_238.js",
    "https://lpl.qq.com/web201612/data/LOL_MATCH2_MATCH_HOMEPAGE_BMATCH_LIST_239.js",
]
GAME_PREFIX_RULES = [
    ("职业联赛", "LPL"),
    ("全球先锋赛", "FST"),
    ("季中冠军赛", "MSI"),
]

def normalize_payload(content):
    """把接口返回内容尽量整理成标准 JSON 字符串"""
    content = content.strip()
    if content.startswith("var"):
        content = content.split('=', 1)[1].strip().rstrip(';')
    return json.loads(content)

def get_field(match, *names, default=""):
    """按多个字段名依次取值，兼容大小写和不同来源字段"""
    for name in names:
        if name in match and match.get(name):
            return match.get(name)
        lower_name = name.lower()
        if lower_name in match and match.get(lower_name):
            return match.get(lower_name)
    return default

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

    return team_a or "未知A", team_b or "未知B"

def get_game_prefix(match):
    """根据 GameName / GameTypeName 映射赛事前缀"""
    game_name = str(get_field(match, "GameName", "GameTypeName", default=""))
    for keyword, prefix in GAME_PREFIX_RULES:
        if keyword in game_name:
            return prefix
    return "LPL"

def get_group_prefix(group_name):
    """根据赛段名称映射前缀，找不到时默认 LPL"""
    group_text = str(group_name or "")
    for keyword, prefix in GAME_PREFIX_RULES:
        if keyword in group_text:
            return prefix
    return "LPL"

def fetch_and_save_raw_json(url, output_path):
    """下载接口并保存原始 JSON"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = normalize_payload(response.text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ 原始数据已成功保存至本地：{output_path.relative_to(BASE_DIR)}")
        return data

    except Exception as e:
        print(f"下载或保存失败: {e}")
        return None

def clear_raw_dir(raw_dir):
    """下载前清空 raw 目录，确保只保留本次抓取的数据"""
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

def load_and_parse_lpl_data(json_paths):
    """统一读取多个本地 JSON 文件并合并解析"""
    group_graphs = {}

    for json_path in json_paths:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"解析失败: {json_path.name} -> {e}")
            continue

        matches = data.get("msg", [])

        for match in matches:
            m = {k.lower(): v for k, v in match.items()}

            if m.get("matchstatus") != "3":
                continue

            group_name = m.get("gamename", "")
            group_name = group_name + m.get("gametypename", "未分类赛段").strip()

            team_a, team_b = parse_teams(m)
            win_side = m.get("matchwin")

            if group_name not in group_graphs:
                group_graphs[group_name] = nx.DiGraph()

            target_graph = group_graphs[group_name]

            if win_side == "1":
                target_graph.add_edge(team_a, team_b)
            elif win_side == "2":
                target_graph.add_edge(team_b, team_a)

    return group_graphs

def merge_raw_json_files(raw_paths, merged_path):
    """把多个 raw JSON 合并成一个 json.json，统一给后续流程使用"""
    merged_matches = []
    seen_match_ids = set()

    for json_path in raw_paths:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"合并失败: {json_path.name} -> {e}")
            continue

        for match in data.get("msg", []):
            match_id = match.get("bMatchId")
            if match_id in seen_match_ids:
                continue
            seen_match_ids.add(match_id)
            merged_matches.append(match)

    merged_matches.sort(key=lambda match: (
        str(get_field(match, "MatchDate", default="")),
        str(get_field(match, "bMatchId", default="")),
    ))

    merged_data = {"msg": merged_matches}
    with open(merged_path, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=4)

    print(f"✅ 已合并生成: {merged_path.relative_to(BASE_DIR)}")
    return merged_path

def display_results(group_graphs):
    if not group_graphs:
        print("没有找到匹配的对局数据。")
        return

    for group_name, G in group_graphs.items():
        group_prefix = get_group_prefix(group_name)
        print(f"\n================ [{group_prefix} {group_name}] 拓扑结构 ================")
        if not G.edges:
            print("该赛段暂无已完成数据。")
            continue
            
        # 打印所有胜负对阵
        for winner, loser in G.edges():
            winner_text = str(winner)
            loser_text = str(loser)
            print(f"  {group_prefix}: {winner_text.ljust(6)}  ➔   {loser_text}")
        
        # 检查循环克制关系（环）
        cycles = list(nx.simple_cycles(G))
        if cycles:
            print(f"\n💡 发现逻辑环（互克关系）:")
            for cycle in cycles:
                if len(cycle) > 2:
                    cycle_text = " -> ".join(str(item) for item in cycle)
                    print(f" {group_prefix} {group_name}  环路({len(cycle)}): {cycle_text} -> {cycle[0]}")

if __name__ == "__main__":
    raw_urls = MATCH_LIST_URLS
    raw_paths = []
    merged_json_path = BASE_DIR / "json.json"

    clear_raw_dir(RAW_DIR)

    for index, url in enumerate(raw_urls, start=1):
        output_path = RAW_DIR / f"json{index}.json"
        data = fetch_and_save_raw_json(url, output_path)
        if data is not None:
            raw_paths.append(output_path)

    if raw_paths:
        merge_raw_json_files(raw_paths, merged_json_path)

    graphs = load_and_parse_lpl_data([merged_json_path] if merged_json_path.exists() else [])
    display_results(graphs)

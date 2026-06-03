import requests
import json
import networkx as nx
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def fetch_and_parse_lpl_data(url):
    try:
        # 1. 获取数据
        response = requests.get(url)
        response.raise_for_status()
        
        # 腾讯有些接口返回的其实是 JS 脚本(包含 var=)，这里做简单的清洗
        content = response.text.strip()
        if content.startswith("var"):
            content = content.split('=', 1)[1].strip().rstrip(';')
            
        data = json.loads(content)
        
        # --- 新增：保存原始 JSON 到本地 ---
        with open(BASE_DIR / 'json.json', 'w', encoding='utf-8') as f:
            # indent=4 让文件带缩进，方便肉眼观察；ensure_ascii=False 保留中文
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("✅ 原始数据已成功保存至本地：json.json")
        # -------------------------------


        # 2. 使用字典存储不同类型的图 { "GameTypeName": DiGraph }
        group_graphs = {}
        
        matches = data.get("msg", [])
        
        for match in matches:
            # --- 关键改进：将所有 Key 转换为小写，解决大小写敏感问题 ---
            m = {k.lower(): v for k, v in match.items()}
            
            # 过滤：只统计已完成的比赛 (MatchStatus 通常为 "3")
            if m.get("matchstatus") != "3":
                continue
                
            # 直接按 GameTypeName 分组
            group_name = m.get("gametypename", "未分类赛段")
            team_a = m.get("teamshortnamea") or "未知A"
            team_b = m.get("teamshortnameb") or "未知B"
            win_side = m.get("matchwin") # "1" 代表 TeamA 胜, "2" 代表 TeamB 胜
            
            # 如果该组别还没创建图，则初始化
            if group_name not in group_graphs:
                group_graphs[group_name] = nx.DiGraph()
            
            target_graph = group_graphs[group_name]

            # 建立胜负关系：胜者 -> 败者
            if win_side == "1":
                target_graph.add_edge(team_a, team_b)
            elif win_side == "2":
                target_graph.add_edge(team_b, team_a)
        
        return group_graphs

    except Exception as e:
        print(f"解析失败: {e}")
        return None

def display_results(group_graphs):
    if not group_graphs:
        print("没有找到匹配的对局数据。")
        return

    for group_name, G in group_graphs.items():
        print(f"\n================ [{group_name}] 拓扑结构 ================")
        if not G.edges:
            print("该赛段暂无已完成数据。")
            continue
            
        # 打印所有胜负对阵
        for winner, loser in G.edges():
            winner_text = str(winner)
            loser_text = str(loser)
            print(f"  {winner_text.ljust(6)}  ➔   {loser_text}")
        
        # 检查循环克制关系（环）
        cycles = list(nx.simple_cycles(G))
        if cycles:
            print(f"\n💡 发现逻辑环（互克关系）:")
            for cycle in cycles:
                print(f" {group_name}  环路({len(cycle)}): {' -> '.join(cycle)} -> {cycle[0]}")

if __name__ == "__main__":
    # 目标 URL
    target_url = "https://lpl.qq.com/web201612/data/LOL_MATCH2_MATCH_HOMEPAGE_BMATCH_LIST_237.js"

    graphs = fetch_and_parse_lpl_data(target_url)
    display_results(graphs)

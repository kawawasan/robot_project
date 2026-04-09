#3hop時のみ検証可能

import sys
import re
import os
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation

def parse_log(filepath):
    data = []
    filename = os.path.basename(filepath)
    node_id = None
    if "CamN" in filename: node_id = "CamN"
    elif "RN1" in filename: node_id = "RN1"
    elif "RN2" in filename: node_id = "RN2"
    elif "CtlN" in filename or "_CN" in filename: node_id = "CtlN"
    if not node_id: return None, None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+)', line)
                if m:
                    data.append({'T': float(m.group(1)), 'Ev': m.group(2), 
                                 'Type': m.group(3), 'Seq': int(m.group(4)), 'Node': node_id})
        return data, node_id
    except: return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 kawamura_analyze_animation.py <log_files...>")
        return

    all_nodes = {}
    first_filename = ""
    for f in sys.argv[1:]:
        logs, nid = parse_log(f)
        if logs: 
            all_nodes[nid] = logs
            if not first_filename: first_filename = os.path.basename(f)

    if not all_nodes:
        print("No valid logs found.")
        return

    # --- 0. 出力ファイル名の決定 ---
    base_experiment_name = re.sub(r'_(CamN|RN2|RN1|CtlN|CN).log$', '', first_filename)
    output_movie = f"sequence_{base_experiment_name}.mp4"

    # --- 1. 時刻補正 (CamN -> RN1 -> RN2 -> CtlN) ---
    offsets = {"CamN": 0.0, "RN1": 0.0, "RN2": 0.0, "CtlN": 0.0}
    MIN_HOP = 0.0005 
    for src, dst in [("CamN", "RN1"), ("RN1", "RN2"), ("RN2", "CtlN")]:
        if src in all_nodes and dst in all_nodes:
            sends = {l['Seq']: l['T'] + offsets[src] for l in all_nodes[src] if l['Type'] == 'VIDEO' and l['Ev'] == 'Send'}
            recvs = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Type'] == 'VIDEO' and l['Ev'] == 'Recv'}
            common = set(sends.keys()) & set(recvs.keys())
            if common:
                offsets[dst] = MIN_HOP - min(recvs[s] - sends[s] for s in common)

    # --- 2. データ準備 ---
    node_order = ["CtlN", "RN2", "RN1", "CamN"]
    x_map = {n: i for i, n in enumerate(node_order)}
    
    # アニメーション設定
    all_times = [l['T'] + offsets[l['Node']] for n in all_nodes.values() for l in n if l['Type'] == 'VIDEO']
    START_TIME = min(all_times) if all_times else 0.0
    DURATION = 10.0    # 10秒間
    FPS = 30           
    WINDOW_SIZE = 0.2  # 画面に見える時間幅 (200ms)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(-0.5, len(node_order) - 0.5)
    ax.set_xticks(range(len(node_order)))
    ax.set_xticklabels(node_order, fontweight='bold')
    ax.invert_yaxis()
    ax.grid(True, axis='y', linestyle=':', alpha=0.5)

    colors = {'VIDEO': "#dc6419", 'CONTROL': "#2352e0"}

    # 全データをあらかじめプロット（線を表示）
    tracks = {}
    for nid, logs in all_nodes.items():
        off = offsets.get(nid, 0.0)
        for l in logs:
            t_corr = l['T'] + off
            if START_TIME <= t_corr <= START_TIME + DURATION + WINDOW_SIZE:
                key = (l['Type'], l['Seq'])
                if l['Type'] in colors:
                    if key not in tracks: tracks[key] = {}
                    tracks[key][x_map[nid]] = t_corr

    for (ptype, seq), node_times in tracks.items():
        sorted_indices = sorted(node_times.keys())
        if len(sorted_indices) > 1:
            ax.plot(sorted_indices, [node_times[i] for i in sorted_indices], 
                    color=colors[ptype], alpha=0.4, linewidth=1)

    def animate(frame):
        t = START_TIME + frame / FPS
        ax.set_ylim(t + WINDOW_SIZE, t)
        ax.set_title(f"MUCViS Animation: {base_experiment_name}\nTime: {t:.2f}s", fontsize=14)
        return []

    num_frames = int(DURATION * FPS)
    ani = FuncAnimation(fig, animate, frames=num_frames, interval=1000/FPS)

    # ローカル保存
    print(f"Creating animation: {output_movie}...")
    writer = FFMpegWriter(fps=FPS, metadata=dict(artist='MUCViS'), bitrate=2000)
    ani.save(output_movie, writer=writer)
    print(f"Successfully saved to {os.getcwd()}/{output_movie}")

if __name__ == "__main__":
    main()
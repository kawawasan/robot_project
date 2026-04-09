import sys, re, os
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation
from matplotlib.collections import LineCollection
import numpy as np

def parse_log(filepath):
    data = []
    filename = os.path.basename(filepath)
    nid = None
    if "CamN" in filename: nid = "CamN"
    elif "RN1" in filename: nid = "RN1"
    elif "RN2" in filename: nid = "RN2"
    elif "CtlN" in filename or "_cn" in filename or "_CN" in filename: nid = "CtlN"
    if not nid: return None, None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+)', line)
                if m:
                    data.append({'T': float(m.group(1)), 'Ev': m.group(2), 
                                 'Type': m.group(3), 'Seq': int(m.group(4)), 'Node': nid})
        return nid, data
    except: return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mucvis_fast_animator.py <log_files...>")
        return

    all_nodes = {}
    first_filename = ""
    for f in sys.argv[1:]:
        nid, logs = parse_log(f)
        if logs:
            all_nodes[nid] = logs
            if not first_filename: first_filename = os.path.basename(f)

    if not all_nodes: return

    # --- 0. 出力ファイル名 ---
    exp_name = re.sub(r'_(CamN|RN2|RN1|CtlN|cn|CN).log$', '', first_filename)
    output_movie = f"sequence_{exp_name}.mp4"

    # --- 1. 時刻同期 (隣接ノード間で全タイプを利用) ---
    offsets = {n: 0.0 for n in ["CtlN", "RN1", "RN2", "CamN"]}
    MIN_HOP = 0.0005
    # CtlN(0)-RN1(1)-RN2(2)-CamN(3) の順で同期
    pairs = [("CtlN", "RN1"), ("RN1", "RN2"), ("RN2", "CamN")]
    for i in range(len(pairs)):
        for src, dst in pairs:
            if src in all_nodes and dst in all_nodes:
                # 送信(src) -> 受信(dst) または 受信(src) <- 送信(dst) の両方で同期を試みる
                s1, r1 = {l['Seq']: l['T'] for l in all_nodes[src] if l['Ev'] == 'Send'}, {l['Seq']: l['T'] for l in all_nodes[dst] if l['Ev'] == 'Recv'}
                s2, r2 = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Ev'] == 'Send'}, {l['Seq']: l['T'] for l in all_nodes[src] if l['Ev'] == 'Recv'}
                
                # 順方向(src->dst)
                common1 = set(s1.keys()) & set(r1.keys()) - {0}
                if common1:
                    raw_min = min(r1[s] - (s1[s] + offsets[src]) for s in common1)
                    offsets[dst] = MIN_HOP - raw_min
                # 逆方向(dst->src)
                common2 = set(s2.keys()) & set(r2.keys()) - {0}
                if common2:
                    raw_min = min(r2[s] - (s2[s] + offsets[dst]) for s in common2)
                    offsets[src] = MIN_HOP - raw_min

    # --- 2. パケット経路集計 ---
    node_order = ["CtlN", "RN1", "RN2", "CamN"]
    x_map = {n: i for i, n in enumerate(node_order)}
    colors = {'VIDEO': "#dc6419", 'CONTROL': "#2352e0"}
    
    tracks = {'VIDEO': [], 'CONTROL': []}
    
    # 全パケットを統合
    all_p_map = {} # (Type, Seq) -> {NodeIdx: Time}
    for nid, logs in all_nodes.items():
        off = offsets[nid]
        for l in logs:
            if l['Type'] not in colors: continue
            if l['Seq'] == 0 and l['Type'] == 'DUMMY': continue
            key = (l['Type'], l['Seq'])
            if key not in all_p_map: all_p_map[key] = {}
            t_corr = l['T'] + off
            if x_map[nid] not in all_p_map[key] or t_corr < all_p_map[key][x_map[nid]]:
                all_p_map[key][x_map[nid]] = t_corr

    # START_TIMEの自動決定
    all_t = [t for p in all_p_map.values() for t in p.values()]
    START_TIME = min(all_t) if all_t else 0.0
    DURATION = 30.0
    WINDOW = 0.4
    END_T = START_TIME + DURATION + WINDOW

    # 描画データを LineCollection 用に整理
    for (ptype, seq), nodes in all_p_map.items():
        if ptype not in colors: continue
        sorted_x = sorted(nodes.keys(), key=lambda x: nodes[x])
        if len(sorted_x) > 1:
            t_min = min(nodes.values())
            if START_TIME <= t_min <= END_T:
                segments = []
                for i in range(len(sorted_x)-1):
                    x1, x2 = sorted_x[i], sorted_x[i+1]
                    segments.append([(x1, nodes[x1]), (x2, nodes[x2])])
                tracks[ptype].extend(segments)

    # --- 3. 高速描画 ---
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(-0.5, 3.5)
    ax.set_xticks(range(4))
    ax.set_xticklabels(node_order, fontweight='bold')
    ax.invert_yaxis()
    ax.grid(True, axis='y', linestyle='--', alpha=0.3)

    # LineCollectionの作成 (これが高速化のキモ)
    lc_video = LineCollection(tracks['VIDEO'], colors=colors['VIDEO'], alpha=0.4, linewidths=1.0)
    lc_ctrl = LineCollection(tracks['CONTROL'], colors=colors['CONTROL'], alpha=0.7, linewidths=1.5)
    ax.add_collection(lc_video)
    ax.add_collection(lc_ctrl)

    def animate(frame):
        t = START_TIME + frame / 30
        ax.set_ylim(t + WINDOW, t)
        ax.set_title(f"MUCViS Trace: {exp_name} | Time: {t:.2f}s", fontsize=12)
        if frame % 30 == 0:
            print(f"Progress: {frame/300*100:.1f}%") # 進行度表示
        return [lc_video, lc_ctrl]

    print(f"Creating animation: {output_movie}...")
    ani = FuncAnimation(fig, animate, frames=300, interval=33, blit=True)
    writer = FFMpegWriter(fps=30, bitrate=3000)
    ani.save(output_movie, writer=writer)
    print(f"Successfully saved to {output_movie}")

if __name__ == "__main__":
    main()
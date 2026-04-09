import sys, re, os
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation

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
                if m: data.append({'T': float(m.group(1)), 'Ev': m.group(2), 'Type': m.group(3), 'Seq': int(m.group(4)), 'Node': nid})
        return nid, data
    except: return None, None

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 mucvis_schematic_animator.py <logs...> <start_t> <duration>")
        return

    req_start = float(sys.argv[-2])
    req_duration = float(sys.argv[-1])
    all_nodes = {}
    for f in sys.argv[1:-2]:
        nid, logs = parse_log(f)
        if logs: all_nodes[nid] = logs

    # --- 1. ローカル時刻同期 (ドリフト対策) ---
    offsets = {n: 0.0 for n in ["CtlN", "RN1", "RN2", "CamN"]}
    MIN_HOP = 0.002 # 見やすさのため、ホップ間の段差を少し強調 (2ms)
    pairs = [("CamN", "RN2"), ("RN2", "RN1"), ("RN1", "CtlN")]
    
    for src, dst in pairs:
        if src in all_nodes and dst in all_nodes:
            s_times = {l['Seq']: l['T'] for l in all_nodes[src] if l['Ev'] == 'Send' and abs(l['T'] - req_start) < 5}
            r_times = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Ev'] == 'Recv' and abs(l['T'] - req_start) < 5}
            common = set(s_times.keys()) & set(r_times.keys()) - {0}
            if common:
                raw_diff = min(r_times[s] - (s_times[s] + offsets[src]) for s in common)
                offsets[dst] = offsets[src] + (MIN_HOP - raw_diff)

    # --- 2. ノード設定と間引きロジック ---
    node_order = ["CtlN", "RN1", "RN2", "CamN"]
    x_map = {n: i for i, n in enumerate(node_order)}
    colors = {'VIDEO': "#dc6419", 'CONTROL': "#2352e0"}
    
    # 見やすさのための間引き設定 (参考画像の間隔を再現)
    VIDEO_SAMPLE_RATE = 25   # 25個に1個描画
    CTRL_SAMPLE_RATE = 1     # 制御は全部(または少ないのでそのまま)
    WINDOW = 0.2 # 200ms

    tracks = []
    p_map = {} # (Type, Seq) -> {NodeIdx: Time}

    for nid, logs in all_nodes.items():
        off = offsets[nid]
        for l in logs:
            # 間引き処理
            if l['Type'] == 'VIDEO' and l['Seq'] % VIDEO_SAMPLE_RATE != 0: continue
            if l['Type'] == 'CONTROL' and l['Seq'] % CTRL_SAMPLE_RATE != 0: continue
            if l['Type'] == 'DUMMY': continue

            t_corr = l['T'] + off
            if req_start <= t_corr <= req_start + req_duration + WINDOW:
                key = (l['Type'], l['Seq'])
                if key not in p_map: p_map[key] = {}
                # 最も早い時刻（そのパケットがそのノードに現れた瞬間）を保持
                if x_map[nid] not in p_map[key] or t_corr < p_map[key][x_map[nid]]:
                    p_map[key][x_map[nid]] = t_corr

    # 経路を整理
    for (ptype, seq), nodes in p_map.items():
        # 物理的な流れに沿ってソート (CONTROL: 0->3, VIDEO: 3->0)
        # ただし、描画は時間順に繋げば自動的に正しい向きになる
        sorted_x = sorted(nodes.keys(), key=lambda x: nodes[x])
        if len(sorted_x) > 1:
            tracks.append({
                'type': ptype,
                'xs': [x for x in sorted_x],
                'ys': [nodes[x] for x in sorted_x]
            })

    # --- 3. 描画設定 ---
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(-0.3, 3.3)
    ax.set_xticks(range(4))
    ax.set_xticklabels(node_order, fontweight='bold', fontsize=12)
    ax.invert_yaxis()
    ax.grid(True, axis='y', linestyle=':', alpha=0.5)

    # 背景に各ノードの縦線を引く
    for i in range(4):
        ax.axvline(i, color='gray', alpha=0.2, lw=1)

    # 全パケットを先にプロット (アニメーションの窓で見せる)
    for tr in tracks:
        ax.plot(tr['xs'], tr['ys'], color=colors[tr['type']], alpha=0.6, linewidth=1.5, zorder=2)
        ax.scatter(tr['xs'], tr['ys'], color=colors[tr['type']], s=25, zorder=3, edgecolors='white', lw=0.5)

    def animate(frame):
        t = req_start + frame / 30
        ax.set_ylim(t + WINDOW, t)
        ax.set_title(f"MUCViS Schematic Trace\nTime: {t:.3f}s (Video sampled 1/{VIDEO_SAMPLE_RATE})", fontsize=12)
        return []

    num_frames = int(req_duration * 30)
    exp_name = re.sub(r'_(CamN|RN2|RN1|CtlN|cn|CN).log$', '', os.path.basename(list(all_nodes.keys())[0]))
    out_file = f"schematic_{exp_name}_t{req_start}.mp4"
    
    print(f"Generating: {out_file}...")
    ani = FuncAnimation(fig, animate, frames=num_frames, interval=33)
    ani.save(out_file, writer=FFMpegWriter(fps=30, bitrate=3000))
    print(f"Success: {out_file}")

if __name__ == "__main__":
    main()
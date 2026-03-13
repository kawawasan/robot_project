import sys
import re
import os
import matplotlib.pyplot as plt

def parse_log(filepath):
    data = []
    filename = os.path.basename(filepath)
    node_id = None
    # 柔軟なノード判定 (CN/CtlNの両方に対応)
    if "CamN" in filename: node_id = "CamN"
    elif "RN1" in filename: node_id = "RN1"
    elif "RN2" in filename: node_id = "RN2"
    elif "CtlN" in filename or "_CN" in filename: node_id = "CtlN"
    
    if not node_id: return None, None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # Type=が無い行(Generate_Command等)を無視し、必要なパケットだけ抽出
                m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+).*PayloadSize=\s*(\d+)', line)
                if m:
                    data.append({
                        'T': float(m.group(1)), 'Ev': m.group(2), 'Type': m.group(3),
                        'Seq': int(m.group(4)), 'Size': int(m.group(5)), 'Node': node_id
                    })
        return data, node_id
    except: return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mucvis_visualize_v3.py <log_files...>")
        return

    all_nodes = {}
    first_filename = ""
    for f in sys.argv[1:]:
        logs, nid = parse_log(f)
        if logs: 
            all_nodes[nid] = logs
            if not first_filename: first_filename = os.path.basename(f)

    if not all_nodes: return

    # --- 0. 出力ファイル名の決定 ---
    base_experiment_name = re.sub(r'_(CamN|RN2|RN1|CtlN|CN).log$', '', first_filename)
    output_pdf = f"sequence_{base_experiment_name}.pdf"

    # --- 1. 時刻補正 (ログの実態: CamN -> RN1 -> RN2 -> CtlN) ---
    offsets = {"CamN": 0.0, "RN1": 0.0, "RN2": 0.0, "CtlN": 0.0}
    MIN_HOP = 0.0005 

    # 実際のホップ順序に合わせて補正
    for src, dst in [("CamN", "RN1"), ("RN1", "RN2"), ("RN2", "CtlN")]:
        if src in all_nodes and dst in all_nodes:
            sends = {l['Seq']: l['T'] + offsets[src] for l in all_nodes[src] if l['Type'] == 'VIDEO' and l['Ev'] == 'Send'}
            recvs = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Type'] == 'VIDEO' and l['Ev'] == 'Recv'}
            common = set(sends.keys()) & set(recvs.keys())
            if common:
                offsets[dst] = MIN_HOP - min(recvs[s] - sends[s] for s in common)

    # --- 2. 可視化設定 ---
    # 横軸の並びもホップ順に合わせる: CtlN (左) --- RN2 --- RN1 --- CamN (右)
    node_order = ["CtlN", "RN2", "RN1", "CamN"]
    x_map = {n: i for i, n in enumerate(node_order)}
    colors = {'VIDEO': "#dc6419", 'CONTROL': "#2352e0", 'DUMMY': 'gray'}
    
    # 描画範囲をパケットがある場所に自動調整
    all_times = [l['T'] + offsets[l['Node']] for n in all_nodes.values() for l in n if l['Type'] == 'VIDEO']
    start_t = min(all_times) if all_times else 0.0
    duration = 0.1 # 100ms
    
    plt.figure(figsize=(12, 10))
    plt.gca().invert_yaxis()

    tracks = {}
    for nid, logs in all_nodes.items():
        off = offsets.get(nid, 0.0)
        for l in logs:
            t_corr = l['T'] + off
            if start_t <= t_corr <= start_t + duration:
                key = (l['Type'], l['Seq'])
                if key not in tracks: tracks[key] = {}
                # 最も早い到達時刻を記録
                if x_map[nid] not in tracks[key] or t_corr < tracks[key][x_map[nid]]:
                    tracks[key][x_map[nid]] = t_corr

    for (ptype, seq), node_times in tracks.items():
        sorted_indices = sorted(node_times.keys())
        if len(sorted_indices) > 1:
            # ノード間を線で結ぶ
            xs = sorted_indices
            ys = [node_times[i] for i in xs]
            plt.plot(xs, ys, color=colors.get(ptype, 'gray'), alpha=0.5, linewidth=1)
        
        for idx, t in node_times.items():
            # パケットタイプでサイズ変更
            s_val = 40 if ptype == 'VIDEO' else 20
            plt.scatter(idx, t, color=colors.get(ptype, 'gray'), s=s_val, zorder=3, edgecolors='white', linewidths=0.5)

    plt.xticks(range(len(node_order)), node_order, fontweight='bold')
    plt.ylabel("Time (s)")
    plt.title(f"Packet Sequence: {base_experiment_name}\n(Window: {duration}s from {start_t:.3f}s)")
    plt.grid(True, axis='y', linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_pdf)
    print(f"Generated: {output_pdf}")

if __name__ == "__main__":
    main()
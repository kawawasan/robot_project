# #3hop時のみ検証可能

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
        print("Usage: python3 mucvis_perfect_trace.py <logs...> <start_t> <duration>")
        return

    req_start = float(sys.argv[-2])
    req_duration = float(sys.argv[-1])
    all_nodes = {}
    for f in sys.argv[1:-2]:
        nid, logs = parse_log(f)
        if logs: all_nodes[nid] = logs

    # --- 1. 時刻同期 (局所的に最適化) ---
    offsets = {n: 0.0 for n in ["CtlN", "RN1", "RN2", "CamN"]}
    MIN_HOP = 0.001 # 見やすさのためホップ間遅延を1msとして描画
    # VIDEOパケットを使って時計を合わせる
    pairs = [("CamN", "RN2"), ("RN2", "RN1"), ("RN1", "CtlN")]
    for src, dst in pairs:
        if src in all_nodes and dst in all_nodes:
            s_times = {l['Seq']: l['T'] for l in all_nodes[src] if l['Type'] == 'VIDEO' and l['Ev'] == 'Send' and abs(l['T'] - req_start) < 2.0}
            r_times = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Type'] == 'VIDEO' and l['Ev'] == 'Recv' and abs(l['T'] - req_start) < 2.0}
            common = set(s_times.keys()) & set(r_times.keys()) - {0}
            if common:
                raw_diff = min(r_times[s] - (s_times[s] + offsets[src]) for s in common)
                offsets[dst] = offsets[src] + (MIN_HOP - raw_diff)

    # --- 2. パケット集計と間引き ---
    node_order = ["CtlN", "RN1", "RN2", "CamN"]
    x_map = {n: i for i, n in enumerate(node_order)}
    colors = {'VIDEO': "#dc6419", 'CONTROL': "#2352e0"}
    
    # 【見やすさの調整】描画するパケットの間隔を設定
    VIDEO_SAMPLE_RATE = 30   # VIDEOは30個に1個だけ描画
    CTRL_SAMPLE_RATE = 1     # CONTROLは数が少ないので全部描画
    WINDOW = 0.1 # 表示する時間幅（100ms）

    p_map = {}
    for nid, logs in all_nodes.items():
        off = offsets[nid]
        for l in logs:
            if l['Type'] == 'DUMMY': continue
            if l['Type'] == 'VIDEO' and l['Seq'] % VIDEO_SAMPLE_RATE != 0: continue
            if l['Type'] == 'CONTROL' and l['Seq'] % CTRL_SAMPLE_RATE != 0: continue

            t_corr = l['T'] + off
            if req_start - 0.1 <= t_corr <= req_start + req_duration + WINDOW:
                key = (l['Type'], l['Seq'])
                if key not in p_map: p_map[key] = {}
                # 最も早い時刻（そのノードに最初に現れた時刻）を記録
                if x_map[nid] not in p_map[key] or t_corr < p_map[key][x_map[nid]]:
                    p_map[key][x_map[nid]] = t_corr

    tracks = []
    # --- 3. 物理経路に沿った結線 (最重要修正ポイント) ---
    for (ptype, seq), nodes in p_map.items():
        if ptype == 'VIDEO':
            # VIDEOは CamN(3) -> RN2(2) -> RN1(1) -> CtlN(0) の順で結ぶ
            path_order = [3, 2, 1, 0]
        else:
            # CONTROLは CtlN(0) -> RN1(1) -> RN2(2) -> CamN(3) の順で結ぶ
            path_order = [0, 1, 2, 3]
        
        xs = []
        ys = []
        # 実際にパケットが存在したノードだけを経路順に抽出
        for n_idx in path_order:
            if n_idx in nodes:
                xs.append(n_idx)
                ys.append(nodes[n_idx])
        
        if len(xs) > 1:
            # 強制的に時間を順方向に補正 (時計の揺れによる逆流描画を防ぐ)
            for i in range(1, len(ys)):
                if ys[i] <= ys[i-1]: ys[i] = ys[i-1] + MIN_HOP
            tracks.append({'type': ptype, 'xs': xs, 'ys': ys})

    # --- 4. 描画 ---
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(-0.3, 3.3)
    ax.set_xticks(range(4))
    ax.set_xticklabels(node_order, fontweight='bold', fontsize=12)
    ax.invert_yaxis()
    ax.grid(True, axis='y', linestyle=':', alpha=0.5)

    # 縦線を引く
    for i in range(4): ax.axvline(i, color='gray', alpha=0.2, lw=1)

    for tr in tracks:
        ax.plot(tr['xs'], tr['ys'], color=colors[tr['type']], alpha=0.7, linewidth=1.5, zorder=2)
        ax.scatter(tr['xs'], tr['ys'], color=colors[tr['type']], s=30, zorder=3, edgecolors='white', lw=0.5)

    def animate(frame):
        t = req_start + frame / 30
        ax.set_ylim(t + WINDOW, t)
        ax.set_title(f"MUCViS Perfect Trace\nTime: {t:.3f}s (Video sampled 1/{VIDEO_SAMPLE_RATE})", fontsize=12)
        return []

    num_frames = int(req_duration * 30)
    exp_name = re.sub(r'_(CamN|RN2|RN1|CtlN|cn|CN).log$', '', os.path.basename(sys.argv[1]))
    out_file = f"perfect_{exp_name}_t{req_start}.mp4"
    
    print(f"Generating: {out_file}...")
    ani = FuncAnimation(fig, animate, frames=num_frames, interval=33)
    ani.save(out_file, writer=FFMpegWriter(fps=30, bitrate=3000))
    print(f"Success: {out_file}")

if __name__ == "__main__":
    main()
    
# import sys
# import re
# import os
# import matplotlib.pyplot as plt

# def parse_log(filepath):
#     data = []
#     filename = os.path.basename(filepath)
#     node_id = None
#     if "CamN" in filename: node_id = "CamN"
#     elif "RN1" in filename: node_id = "RN1"
#     elif "RN2" in filename: node_id = "RN2"
#     elif "CN" in filename: node_id = "CN"
#     if not node_id: return None, None
#     try:
#         with open(filepath, 'r', encoding='utf-8') as f:
#             for line in f:
#                 m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+).*PayloadSize=\s*(\d+)', line)
#                 if m:
#                     data.append({
#                         'T': float(m.group(1)), 'Ev': m.group(2), 'Type': m.group(3),
#                         'Seq': int(m.group(4)), 'Size': int(m.group(5)), 'Node': node_id
#                     })
#         return data, node_id
#     except: return None, None

# def main():
#     if len(sys.argv) < 2:
#         print("Usage: python3 mucvis_visualize.py <log_files...>")
#         return

#     all_nodes = {}
#     for f in sys.argv[1:]:
#         logs, nid = parse_log(f)
#         if logs: all_nodes[nid] = logs

#     # --- 1. 時刻補正 (最小遅延 0.5ms 基準) ---
#     offsets = {"CamN": 0.0, "RN2": 0.0, "RN1": 0.0, "CN": 0.0}
#     MIN_HOP = 0.0005 

#     # CamN -> RN1 -> RN2 -> CN の順で補正
#     for src, dst in [("CamN", "RN2"), ("RN2", "RN1"), ("RN1", "CN")]:
#         if src in all_nodes and dst in all_nodes:
#             sends = {l['Seq']: l['T'] + offsets[src] for l in all_nodes[src] if l['Type'] == 'VIDEO' and l['Ev'] == 'Send'}
#             recvs = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Type'] == 'VIDEO' and l['Ev'] == 'Recv'}
#             common = set(sends.keys()) & set(recvs.keys())
#             if common:
#                 offsets[dst] = MIN_HOP - min(recvs[s] - sends[s] for s in common)

#     # --- 2. 可視化設定 ---
#     node_order = ["CN", "RN1", "RN2", "CamN"] # 横軸
#     x_map = {n: i for i, n in enumerate(node_order)}
#     colors = {'VIDEO': "#e67f24", 'CONTROL': "#3420e6", 'DUMMY': 'gray'}
    
#     # 表示する時間範囲 (秒) を指定。全期間だと重なるため
#     start_t = 3.71
#     duration = 0.1 # 100ms分を表示
    
#     plt.figure(figsize=(10, 12))
#     plt.gca().invert_yaxis() # 縦軸を下向き（時間が進む方向）にする

#     tracks = {} # (Type, Seq) -> {NodeIdx: Time}
#     for nid, logs in all_nodes.items():
#         off = offsets.get(nid, 0.0)
#         for l in logs:
#             t_corr = l['T'] + off
#             if start_t <= t_corr <= start_t + duration:
#                 key = (l['Type'], l['Seq'])
#                 if key not in tracks: tracks[key] = {}
#                 if x_map[nid] not in tracks[key]: tracks[key][x_map[nid]] = t_corr

#     for (ptype, seq), node_times in tracks.items():
#         sorted_indices = sorted(node_times.keys())
#         if len(sorted_indices) > 1:
#             xs = sorted_indices
#             ys = [node_times[i] for i in xs]
#             plt.plot(xs, ys, color=colors.get(ptype, 'gray'), alpha=0.5, linewidth=1)
#         for idx, t in node_times.items():
#             s_val = 30 if ptype == 'VIDEO' else 15
#             plt.scatter(idx, t, color=colors.get(ptype, 'gray'), s=s_val, zorder=3)

#     plt.xticks(range(len(node_order)), node_order)
#     plt.ylabel("Corrected Time (s)")
#     plt.title(f"MUCViS Packet Sequence Diagram (Window: {duration}s)")
#     plt.grid(True, axis='y', linestyle=':', alpha=0.5)
#     plt.savefig('sequence_diagram.pdf')
#     print(f"Success: 'sequence_diagram.pdf' has been saved in {os.getcwd()}")

# if __name__ == "__main__":
#     main()



# import sys
# import re
# import os
# import matplotlib.pyplot as plt

# def parse_log(filepath):
#     data = []
#     filename = os.path.basename(filepath)
#     node_id = None
#     # 柔軟なノード判定 (CN/CtlNの両方に対応)
#     if "CamN" in filename: node_id = "CamN"
#     elif "RN1" in filename: node_id = "RN1"
#     elif "RN2" in filename: node_id = "RN2"
#     elif "CtlN" in filename or "_CN" in filename: node_id = "CtlN"
    
#     if not node_id: return None, None
#     try:
#         with open(filepath, 'r', encoding='utf-8') as f:
#             for line in f:
#                 # Type=が無い行(Generate_Command等)を無視し、必要なパケットだけ抽出
#                 m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+).*PayloadSize=\s*(\d+)', line)
#                 if m:
#                     data.append({
#                         'T': float(m.group(1)), 'Ev': m.group(2), 'Type': m.group(3),
#                         'Seq': int(m.group(4)), 'Size': int(m.group(5)), 'Node': node_id
#                     })
#         return data, node_id
#     except: return None, None

# def main():
#     if len(sys.argv) < 2:
#         print("Usage: python3 mucvis_visualize_v3.py <log_files...>")
#         return

#     all_nodes = {}
#     first_filename = ""
#     for f in sys.argv[1:]:
#         logs, nid = parse_log(f)
#         if logs: 
#             all_nodes[nid] = logs
#             if not first_filename: first_filename = os.path.basename(f)

#     if not all_nodes: return

#     # --- 0. 出力ファイル名の決定 ---
#     base_experiment_name = re.sub(r'_(CamN|RN2|RN1|CtlN|CN).log$', '', first_filename)
#     output_pdf = f"sequence_{base_experiment_name}.pdf"

#     # --- 1. 時刻補正 (ログの実態: CamN -> RN1 -> RN2 -> CtlN) ---
#     offsets = {"CamN": 0.0, "RN1": 0.0, "RN2": 0.0, "CtlN": 0.0}
#     MIN_HOP = 0.0005 

#     # 実際のホップ順序に合わせて補正
#     for src, dst in [("CamN", "RN1"), ("RN1", "RN2"), ("RN2", "CtlN")]:
#         if src in all_nodes and dst in all_nodes:
#             sends = {l['Seq']: l['T'] + offsets[src] for l in all_nodes[src] if l['Type'] == 'VIDEO' and l['Ev'] == 'Send'}
#             recvs = {l['Seq']: l['T'] for l in all_nodes[dst] if l['Type'] == 'VIDEO' and l['Ev'] == 'Recv'}
#             common = set(sends.keys()) & set(recvs.keys())
#             if common:
#                 offsets[dst] = MIN_HOP - min(recvs[s] - sends[s] for s in common)

#     # --- 2. 可視化設定 ---
#     # 横軸の並びもホップ順に合わせる: CtlN (左) --- RN2 --- RN1 --- CamN (右)
#     node_order = ["CtlN", "RN2", "RN1", "CamN"]
#     x_map = {n: i for i, n in enumerate(node_order)}
#     colors = {'VIDEO': "#dc6419", 'CONTROL': "#2352e0", 'DUMMY': 'gray'}
    
#     # 描画範囲をパケットがある場所に自動調整
#     all_times = [l['T'] + offsets[l['Node']] for n in all_nodes.values() for l in n if l['Type'] == 'VIDEO']
#     start_t = min(all_times) if all_times else 0.0
#     duration = 30 # 100ms
    
#     plt.figure(figsize=(12, 10))
#     plt.gca().invert_yaxis()

#     tracks = {}
#     for nid, logs in all_nodes.items():
#         off = offsets.get(nid, 0.0)
#         for l in logs:
#             t_corr = l['T'] + off
#             if start_t <= t_corr <= start_t + duration:
#                 key = (l['Type'], l['Seq'])
#                 if key not in tracks: tracks[key] = {}
#                 # 最も早い到達時刻を記録
#                 if x_map[nid] not in tracks[key] or t_corr < tracks[key][x_map[nid]]:
#                     tracks[key][x_map[nid]] = t_corr

#     for (ptype, seq), node_times in tracks.items():
#         sorted_indices = sorted(node_times.keys())
#         if len(sorted_indices) > 1:
#             # ノード間を線で結ぶ
#             xs = sorted_indices
#             ys = [node_times[i] for i in xs]
#             plt.plot(xs, ys, color=colors.get(ptype, 'gray'), alpha=0.5, linewidth=1)
        
#         for idx, t in node_times.items():
#             # パケットタイプでサイズ変更
#             s_val = 40 if ptype == 'VIDEO' else 20
#             plt.scatter(idx, t, color=colors.get(ptype, 'gray'), s=s_val, zorder=3, edgecolors='white', linewidths=0.5)

#     plt.xticks(range(len(node_order)), node_order, fontweight='bold')
#     plt.ylabel("Time (s)")
#     plt.title(f"Packet Sequence: {base_experiment_name}\n(Window: {duration}s from {start_t:.3f}s)")
#     plt.grid(True, axis='y', linestyle=':', alpha=0.6)
#     plt.tight_layout()
#     plt.savefig(output_pdf)
#     print(f"Generated: {output_pdf}")

# if __name__ == "__main__":
#     main()
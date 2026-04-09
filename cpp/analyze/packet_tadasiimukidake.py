import sys, os, re
import matplotlib.pyplot as plt
import pandas as pd

def parse_log(file_path):
    fname = os.path.basename(file_path).lower()
    if "cn" in fname or "ctln" in fname: node = "CtlN"
    elif "rn1" in fname: node = "RN1"
    elif "rn2" in fname: node = "RN2"
    elif "camn" in fname: node = "CamN"
    else: return None, [], 0

    data, t_zero = [], 0
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "time_pref_counter=" in line:
                t_zero = int(line.split("time_pref_counter=")[1].strip())
            
            if "T=" not in line or "Seq=" not in line: continue
            if "Ev= Send" not in line and "Ev= Recv" not in line: continue
                
            try:
                t = float(re.search(r'T=\s*([\d.]+)', line).group(1))
                ptype = re.search(r'Type=\s*(\w+)', line).group(1)
                seq = int(re.search(r'Seq=\s*(\d+)', line).group(1))
                ev = "Send" if "Ev= Send" in line else "Recv"
                
                # パケットの送信方向（Up/Down）を取得
                dir_m = re.search(r'Direction=\s*(\w+)', line)
                direction = dir_m.group(1) if dir_m else None
                
                sys_m = re.search(r'SystemTime=\s*(\d+)', line)
                sys_time = int(sys_m.group(1)) if sys_m else t_zero + int(t * 1e9)
                data.append({
                    'Type': ptype, 'Seq': seq, 'SystemTime': sys_time, 
                    'Node': node, 'Event': ev, 'Direction': direction
                })
            except: continue
    return node, data, t_zero

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 packet_analyze.py [log_files...] start_t window_size")
        return
    
    log_files = sys.argv[1:-2]
    start_t = float(sys.argv[-2])
    window_size = float(sys.argv[-1])
    
    all_raw, counters = {}, {}
    for f in log_files:
        name, d, c = parse_log(f)
        if name:
            all_raw[name] = d
            counters[name] = c

    base = "CtlN"
    offsets = {n: 0 for n in all_raw}

    # イベントを取得する際、正しい「Direction」の送信のみを取得するよう改良
    def get_event_st(node, ptype, seq, event):
        if node not in all_raw: return None
        for d in all_raw[node]:
            if d['Type'] == ptype and d['Seq'] == seq and d['Event'] == event:
                # 中継ノードの不要な折り返し送信(エコー)を無視する
                if event == "Send" and d['Direction'] is not None:
                    if ptype == "CONTROL" and d['Direction'] != "Up":
                        continue
                    if ptype in ["VIDEO", "DUMMY"] and d['Direction'] != "Down":
                        continue
                return d['SystemTime']
        return None

    # NTP-style Synchronization
    v0_base = get_event_st(base, "VIDEO", 0, "Recv")
    c0_base = get_event_st(base, "CONTROL", 0, "Send")
    
    print(f"--- NTP Sync Adjustments (Base: {base}) ---")
    for n in all_raw:
        if n == base: continue
        
        vn = get_event_st(n, "VIDEO", 0, "Send")
        cn = get_event_st(n, "CONTROL", 0, "Recv")
        
        if vn and cn and v0_base and c0_base:
            offsets[n] = ((v0_base - vn) - (cn - c0_base)) // 2
            print(f"Node {n:<4} offset: {offsets[n]:>12} ns ({(offsets[n]/1e6):.2f} ms)")
        else:
            print(f"Node {n:<4} offset: Could not sync")

    # Data Processing
    processed = []
    base_counter = counters.get(base, 0)
    
    for n, entries in all_raw.items():
        for d in entries:
            # 描画対象のイベントをフィルター（逆向きの送信を除外）
            if d['Event'] == "Send" and d['Direction'] is not None:
                if d['Type'] == "CONTROL" and d['Direction'] != "Up":
                    continue
                if d['Type'] in ["VIDEO", "DUMMY"] and d['Direction'] != "Down":
                    continue
            # 受信イベントも、複数ある場合は最初の1つだけにするための処理を後でpandasで行う
                    
            adj_t = (d['SystemTime'] + offsets[n] - base_counter) / 1e9
            if start_t <= adj_t <= start_t + window_size:
                processed.append({
                    'Node': n, 
                    'Type': d['Type'], 
                    'Seq': d['Seq'], 
                    'Time': adj_t,
                    'Event': d['Event']
                })
    
    df = pd.DataFrame(processed)
    if df.empty:
        return print("範囲内にパケットが見つかりませんでした。")

    # 各ノードでの重複イベント（Recvなど）を間引き、純粋に「最初」の処理だけを残す
    df = df.sort_values('Time').groupby(['Type', 'Seq', 'Node', 'Event']).first().reset_index()

    node_order = ["CtlN", "RN1", "RN2", "CamN"]
    
    # Drawing
    fig, ax = plt.subplots(figsize=(12, 8))
    colors = {"VIDEO": "orange", "CONTROL": "blue", "DUMMY": "lightgray"}
    
    for (ptype, seq), group in df.groupby(['Type', 'Seq']):
        group = group.sort_values(by='Time')
        
        if len(group) < 2: continue
            
        x_vals, y_vals = [], []
        for _, row in group.iterrows():
            if row['Node'] in node_order:
                x_vals.append(node_order.index(row['Node']))
                y_vals.append(row['Time'])
        
        ax.plot(x_vals, y_vals, color=colors.get(ptype, "black"), linewidth=1.0, alpha=0.8)
        ax.scatter(x_vals, y_vals, color=colors.get(ptype, "black"), s=15, zorder=3)

    ax.set_xticks(range(len(node_order)))
    ax.set_xticklabels(node_order, fontsize=12, fontweight='bold')
    ax.set_ylabel("Time (s)", fontsize=12)
    ax.set_ylim(start_t + window_size, start_t) 
    ax.set_title(f"High-Precision Sequence Diagram ({start_t}s - {start_t+window_size}s)", fontsize=14)
    ax.grid(True, axis='y', linestyle='--', alpha=0.5)
    ax.grid(True, axis='x', linestyle=':', alpha=0.3)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
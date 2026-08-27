import sys
import re
import os

def parse_log(filepath):
    data = []
    filename = os.path.basename(filepath)
    node_id = None
    if "CamN" in filename: node_id = "CamN"
    elif "RN1" in filename: node_id = "RN1"
    elif "RN2" in filename: node_id = "RN2"
    elif "CN" in filename or "CtlN" in filename: node_id = "CtlN"
            
    if not node_id: return None, None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+).*PayloadSize=\s*(\d+)', line)
                if m:
                    data.append({
                        'T': float(m.group(1)), 'Ev': m.group(2), 
                        'Type': m.group(3), 'Seq': int(m.group(4)), 
                        'Size': int(m.group(5)), 'Node': node_id
                    })
        return data, node_id
    except Exception as e:
        print(f"Error reading {node_id}: {e}", file=sys.stderr)
        return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_dynamic_timeseries.py <logs...>", file=sys.stderr)
        return

    nodes = {}
    for arg in sys.argv[1:]:
        logs, node_id = parse_log(arg)
        if logs: nodes[node_id] = logs

    # パケットの物理的な並び順（送信元から宛先へ）
    # ユーザー指摘通り: CtlN - RN1 - RN2 - CamN 
    # つまり、CamNから見ると RN2 -> RN1 -> CtlN の順になる
    configs = [
        {"type": "VIDEO", "order": ["CamN", "RN2", "RN1", "CtlN"]},
        {"type": "CONTROL", "order": ["CtlN", "RN1", "RN2", "CamN"]}
    ]

    INTERVAL_SEC = 1.0 
    try:
        min_t = min(d['T'] for log in nodes.values() for d in log)
    except ValueError:
        return

    ts_data = {}
    all_bins = set()

    for cfg in configs:
        p_type = cfg["type"]
        path_order = cfg["order"]
        dest_node = path_order[-1] # 最終目的地
        src_node = path_order[0]   # 最初の送信元

        # 1. パケット(Seq)ごとに、誰が送信(Send)したかを記録
        sends_by_seq = {}
        for node_id in path_order:
            if node_id not in nodes: continue
            for log in nodes[node_id]:
                if log['Type'] == p_type and log['Ev'] == 'Send':
                    seq = log['Seq']
                    if seq not in sends_by_seq:
                        sends_by_seq[seq] = set()
                    sends_by_seq[seq].add(node_id)

        # 2. 受信(Recv)イベントごとに、直前の送信者を特定する
        for node_id in path_order:
            if node_id not in nodes: continue
            for log in nodes[node_id]:
                if log['Type'] == p_type and log['Ev'] == 'Recv':
                    seq = log['Seq']
                    recv_idx = path_order.index(node_id)
                    
                    if recv_idx == 0: continue

                    # 誰から送られてきたかを動的に判定
                    sender_node = None
                    if seq in sends_by_seq:
                        for i in range(recv_idx - 1, -1, -1):
                            if path_order[i] in sends_by_seq[seq]:
                                sender_node = path_order[i]
                                break
                    
                    # 🌟【修正】bin_idx の計算をここに出す（送信元が不明でも時間は記録する）
                    bin_idx = int((log['T'] - min_t) / INTERVAL_SEC)
                    all_bins.add(bin_idx)

                    if sender_node:
                        # 区間のスループットを加算
                        seg_name = f"{sender_node}->{node_id}({p_type})"
                        if seg_name not in ts_data: ts_data[seg_name] = {}
                        ts_data[seg_name][bin_idx] = ts_data[seg_name].get(bin_idx, 0) + log['Size'] * 8

                    # End-to-End スループットの計算（最終目的地に届いたものだけ）
                    if node_id == dest_node:
                        e2e_name = f"{src_node}-{dest_node}({p_type}_E2E)"
                        if e2e_name not in ts_data: ts_data[e2e_name] = {}
                        # 🌟 これで未定義エラーを回避できる
                        ts_data[e2e_name][bin_idx] = ts_data[e2e_name].get(bin_idx, 0) + log['Size'] * 8
    if not all_bins: return
    max_bin = max(all_bins)
    segment_names = sorted(ts_data.keys())
    
    print(",".join(["Time(s)"] + segment_names))
    for bin_idx in range(max_bin + 1):
        row = [f"{bin_idx * INTERVAL_SEC:.1f}"]
        for seg in segment_names:
            throughput_mbps = (ts_data[seg].get(bin_idx, 0) / INTERVAL_SEC) / 1_000_000
            row.append(f"{throughput_mbps:.4f}")
        print(",".join(row))

if __name__ == "__main__":
    main()
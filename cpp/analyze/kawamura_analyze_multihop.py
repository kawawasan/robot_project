import sys
import re
import os

def parse_log(filepath):
    data = []
    filename = os.path.basename(filepath)
    
    # ノード名の特定（大文字小文字を区別せず、ファイル名に含まれるかチェック）
    node_id = None
    if "CamN" in filename: node_id = "CamN"
    elif "RN1" in filename: node_id = "RN1"
    elif "RN2" in filename: node_id = "RN2"
    elif "CN" in filename: node_id = "CN"
            
    if not node_id:
        return None, None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # 柔軟な正規表現（空白の有無に対応）
                m = re.search(r'T=\s*([\d\.]+).*Ev=\s*(\w+).*Type=\s*(\w+).*Seq=\s*(\d+).*PayloadSize=\s*(\d+)', line)
                if m:
                    data.append({
                        'T': float(m.group(1)),
                        'Ev': m.group(2),
                        'Type': m.group(3),
                        'Seq': int(m.group(4)),
                        'Size': int(m.group(5))
                    })
        return data, node_id
    except Exception as e:
        print(f"Error reading {node_id}: {e}")
        return None, None

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_fixed_multihop.py <logs...>")
        return

    nodes = {}
    for arg in sys.argv[1:]:
        logs, node_id = parse_log(arg)
        if logs:
            nodes[node_id] = logs

    # 解析順序の定義
    configs = [
        {"label": "映像データ (VIDEO)", "type": "VIDEO", "order": ["CamN", "RN1", "RN2", "CN"]},
        {"label": "制御用データ (CONTROL)", "type": "CONTROL", "order": ["CN", "RN2", "RN1", "CamN"]}
    ]

    MIN_PER_HOP_MS = 0.5

    for cfg in configs:
        p_type = cfg["type"]
        path = [n for n in cfg["order"] if n in nodes]
        if len(path) < 2: continue
            
        print(f"\n=== {cfg['label']} ===")
        print(f"解析パス: {' -> '.join(path)}")
        print("-" * 60)

        # ホップごとの解析を実行
        for i in range(len(path) - 1):
            src_n, dst_n = path[i], path[i+1]
            src_sends = {d['Seq']: d['T'] for d in nodes[src_n] if d['Type'] == p_type and d['Ev'] == 'Send'}
            dst_recvs = {d['Seq']: d['T'] for d in nodes[dst_n] if d['Type'] == p_type and d['Ev'] == 'Recv'}
            
            common_seqs = sorted(list(set(src_sends.keys()) & set(dst_recvs.keys())))
            if not common_seqs:
                print(f"区間 [{src_n} -> {dst_n}]: データが一致しません")
                continue

            raw_delays = [(dst_recvs[s] - src_sends[s]) * 1000 for s in common_seqs]
            offset = MIN_PER_HOP_MS - min(raw_delays)
            fixed_delays = [d + offset for d in raw_delays]
            
            avg = sum(fixed_delays) / len(fixed_delays)
            jitter = sum(abs(fixed_delays[j] - fixed_delays[j-1]) for j in range(1, len(fixed_delays))) / (len(fixed_delays) - 1) if len(fixed_delays) > 1 else 0
            loss = (1 - len(common_seqs) / len(src_sends)) * 100 if len(src_sends) > 0 else 0
            
            print(f"区間 [{src_n} -> {dst_n}]:")
            print(f"  補正オフセット: {offset:8.4f} ms")
            print(f"  平均遅延(補正): {avg:8.4f} ms")
            print(f"  ジッタ        : {jitter:8.4f} ms")
            print(f"  ロス率        : {loss:6.2f} %")
            print()

        # End-to-End の計算
        src_e2e, dst_e2e = path[0], path[-1]
        e2e_sends = {d['Seq']: d['T'] for d in nodes[src_e2e] if d['Type'] == p_type and d['Ev'] == 'Send'}
        e2e_recvs = {d['Seq']: d['T'] for d in nodes[dst_e2e] if d['Type'] == p_type and d['Ev'] == 'Recv'}
        common_e2e = set(e2e_sends.keys()) & set(e2e_recvs.keys())
        
        if common_e2e:
            num_hops = len(path) - 1
            e2e_raw = [(e2e_recvs[s] - e2e_sends[s]) * 1000 for s in common_e2e]
            # E2Eの最小値は ホップ数 * 0.5ms と仮定
            e2e_offset = (num_hops * MIN_PER_HOP_MS) - min(e2e_raw)
            e2e_fixed = [d + e2e_offset for d in e2e_raw]
            
            print(f"--- End-to-End ({src_e2e} -> {dst_e2e}) ---")
            print(f"  平均全遅延(補正): {sum(e2e_fixed)/len(e2e_fixed):8.4f} ms")

if __name__ == "__main__":
    main()
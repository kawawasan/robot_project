import sys
import re
from collections import defaultdict

def parse_log(filename):
    data = []
    node_id = filename.split('/')[-1].split('.')[0]
    if '_' in node_id:
        node_id = node_id.split('_')[-1]
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                m = re.search(r'T=\s+([\d\.]+)\s+Ev=\s+(\w+)\s+Type=\s+(\w+)\s+ACK=\s+(\d+)\s+Seq=\s+(\d+)\s+PayloadSize=\s+(\d+)', line)
                if m:
                    data.append({
                        'T': float(m.group(1)),
                        'Ev': m.group(2),
                        'Type': m.group(3),
                        'Seq': int(m.group(5)),
                        'Size': int(m.group(6)),
                        'Node': node_id
                    })
    except Exception as e:
        print(f"Error reading {filename}: {e}")
    return data, node_id

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_fixed.py <CamN RN1 RN2 CtlN>")
        return

    nodes = {}
    for arg in sys.argv[1:]:
        logs, node_id = parse_log(arg)
        if logs:
            nodes[node_id] = logs

    # 解析設定
    configs = [
        {"label": "映像データ (VIDEO)", "type": "VIDEO", "order": ["CamN", "RN1", "RN2", "CN"]},
        {"label": "制御用データ (CONTROL)", "type": "CONTROL", "order": ["CN", "RN2", "RN1", "CamN"]}
    ]

    # 現実的な最小伝送遅延の仮定 (0.5ms)
    MIN_POSSIBLE_DELAY_MS = 0.5

    for cfg in configs:
        p_type = cfg["type"]
        path = [n for n in cfg["order"] if n in nodes]
        if len(path) < 2: continue
            
        print(f"=== {cfg['label']} ===")
        print(f"解析パス: {' -> '.join(path)}")
        print("-" * 50)

        for i in range(len(path) - 1):
            src_n, dst_n = path[i], path[i+1]
            src_sends = {d['Seq']: d['T'] for d in nodes[src_n] if d['Type'] == p_type and d['Ev'] == 'Send'}
            dst_recvs = {d['Seq']: d['T'] for d in nodes[dst_n] if d['Type'] == p_type and d['Ev'] == 'Recv'}
            
            common_seqs = sorted(list(set(src_sends.keys()) & set(dst_recvs.keys())))
            if not common_seqs: continue

            # 1. 生の遅延を計算
            raw_delays = [ (dst_recvs[s] - src_sends[s]) * 1000 for s in common_seqs ]
            
            # 2. 補正値（オフセット）の算出
            # 最も速いパケットが MIN_POSSIBLE_DELAY_MS になるように調整
            min_raw_delay = min(raw_delays)
            offset = MIN_POSSIBLE_DELAY_MS - min_raw_delay
            
            # 3. 全パケットを補正
            fixed_delays = [ d + offset for d in raw_delays ]
            
            # 統計計算
            avg_delay = sum(fixed_delays) / len(fixed_delays)
            jitter = sum(abs(fixed_delays[j] - fixed_delays[j-1]) for j in range(1, len(fixed_delays))) / (len(fixed_delays) - 1) if len(fixed_delays) > 1 else 0
            
            # ロス率
            sent_count = len(src_sends)
            lost_count = len(set(src_sends.keys()) - set(dst_recvs.keys()))
            loss_rate = (lost_count / sent_count * 100) if sent_count > 0 else 0
            
            # スループット
            dst_pkts = sorted([d for d in nodes[dst_n] if d['Type'] == p_type and d['Ev'] == 'Recv'], key=lambda x: x['T'])
            thr = 0
            if len(dst_pkts) > 1:
                duration = dst_pkts[-1]['T'] - dst_pkts[0]['T']
                total_bits = sum(d['Size'] for d in dst_pkts) * 8
                thr = (total_bits / duration) / 1e6

            print(f"区間 [{src_n} -> {dst_n}]:")
            print(f"  補正オフセット: {offset:8.4f} ms")
            print(f"  ロス率        : {loss_rate:6.2f} % ({lost_count}/{sent_count})")
            print(f"  平均遅延(補正): {avg_delay:8.4f} ms")
            print(f"  ジッタ        : {jitter:8.4f} ms")
            print(f"  スループット  : {thr:8.4f} Mbps")
            print()

        # End-to-End の計算 (最初の送信ノードから最後の受信ノードまで)
        e2e_src, e2e_dst = path[0], path[-1]
        e2e_sends = {d['Seq']: d['T'] for d in nodes[e2e_src] if d['Type'] == p_type and d['Ev'] == 'Send'}
        e2e_recvs = {d['Seq']: d['T'] for d in nodes[e2e_dst] if d['Type'] == p_type and d['Ev'] == 'Recv'}
        e2e_common = set(e2e_sends.keys()) & set(e2e_recvs.keys())
        
        if e2e_common:
            # E2Eでも同様に最小遅延を基準に補正（物理的な最小値はホップ数分程度と仮定）
            e2e_raw = [ (e2e_recvs[s] - e2e_sends[s]) * 1000 for s in e2e_common ]
            e2e_offset = (len(path)-1) * MIN_POSSIBLE_DELAY_MS - min(e2e_raw)
            e2e_fixed = [ d + e2e_offset for d in e2e_raw ]
            
            print(f"--- End-to-End ({e2e_src} -> {e2e_dst}) ---")
            print(f"  平均全遅延(補正): {sum(e2e_fixed)/len(e2e_fixed):8.4f} ms")
            print("\n")

if __name__ == "__main__":
    main()
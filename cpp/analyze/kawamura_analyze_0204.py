import sys
import re
from collections import defaultdict

def parse_log(filename):
    data = []
    # ファイル名からノードの識別子（CamN, RN2, RN1, CN）を抽出
    node_id = filename.split('/')[-1].split('.')[0]
    if '_' in node_id:
        node_id = node_id.split('_')[-1]
        
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                # T, Ev, Type, ACK, Seq, Sizeを抽出
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
        print("Usage: python3 analyze_all.py <logs...>")
        return

    nodes = {}
    for arg in sys.argv[1:]:
        logs, node_id = parse_log(arg)
        if logs:
            nodes[node_id] = logs

    # 解析設定: [パケットタイプ, 順路]
    configs = [
        {"label": "映像データ (VIDEO)", "type": "VIDEO", "order": ["CamN", "RN2", "RN1", "CN"]},
        {"label": "制御用データ (CONTROL)", "type": "CONTROL", "order": ["CN", "RN1", "RN2", "CamN"]}
    ]

    for cfg in configs:
        p_type = cfg["type"]
        # 実際にログが存在するノードだけでパスを構成
        path = [n for n in cfg["order"] if n in nodes]
        
        if len(path) < 2:
            continue
            
        print(f"=== {cfg['label']} ===")
        print(f"解析パス: {' -> '.join(path)}")
        print("-" * 50)

        # 1. ホップごとの解析
        for i in range(len(path) - 1):
            src_n, dst_n = path[i], path[i+1]
            
            # Seq番号をキーに、送信時刻と受信時刻をマッピング
            src_sends = {d['Seq']: d['T'] for d in nodes[src_n] if d['Type'] == p_type and d['Ev'] == 'Send'}
            dst_recvs = {d['Seq']: d['T'] for d in nodes[dst_n] if d['Type'] == p_type and d['Ev'] == 'Recv'}
            
            # 共通して存在するSeq（到達したパケット）
            common_seqs = sorted(list(set(src_sends.keys()) & set(dst_recvs.keys())))
            
            # ロス計算
            sent_count = len(src_sends)
            lost_count = len(set(src_sends.keys()) - set(dst_recvs.keys()))
            loss_rate = (lost_count / sent_count * 100) if sent_count > 0 else 0
            
            # 遅延とジッタ
            delays = [ (dst_recvs[s] - src_sends[s]) * 1000 for s in common_seqs ]
            avg_delay = sum(delays) / len(delays) if delays else 0
            jitter = sum(abs(delays[j] - delays[j-1]) for j in range(1, len(delays))) / (len(delays) - 1) if len(delays) > 1 else 0
            
            # スループット (受信側で計測)
            dst_pkts = sorted([d for d in nodes[dst_n] if d['Type'] == p_type and d['Ev'] == 'Recv'], key=lambda x: x['T'])
            if len(dst_pkts) > 1:
                duration = dst_pkts[-1]['T'] - dst_pkts[0]['T']
                total_bits = sum(d['Size'] for d in dst_pkts) * 8
                thr = (total_bits / duration) / 1e6
            else:
                thr = 0

            print(f"区間 [{src_n} -> {dst_n}]:")
            print(f"  ロス率      : {loss_rate:6.2f} % ({lost_count}/{sent_count})")
            print(f"  平均遅延    : {avg_delay:8.4f} ms")
            print(f"  ジッタ      : {jitter:8.4f} ms")
            print(f"  スループット: {thr:8.4f} Mbps")
            print()

        # 2. End-to-End (全体の最初から最後まで)
        e2e_src, e2e_dst = path[0], path[-1]
        e2e_sends = {d['Seq']: d['T'] for d in nodes[e2e_src] if d['Type'] == p_type and d['Ev'] == 'Send'}
        e2e_recvs = {d['Seq']: d['T'] for d in nodes[e2e_dst] if d['Type'] == p_type and d['Ev'] == 'Recv'}
        e2e_common = set(e2e_sends.keys()) & set(e2e_recvs.keys())
        e2e_delays = [ (e2e_recvs[s] - e2e_sends[s]) * 1000 for s in e2e_common ]
        e2e_loss = (len(set(e2e_sends.keys()) - set(e2e_recvs.keys())) / len(e2e_sends) * 100) if e2e_sends else 0
        
        print(f"--- End-to-End ({e2e_src} -> {e2e_dst}) ---")
        print(f"  通算ロス率  : {e2e_loss:6.2f} %")
        print(f"  平均全遅延  : {sum(e2e_delays)/len(e2e_delays) if e2e_delays else 0:8.4f} ms")
        print("\n")

if __name__ == "__main__":
    main()
import sys
import re
from collections import defaultdict

def parse_log(filename):
    """ログファイルを解析し、パケット情報を抽出する"""
    data = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                # 正規表現で各フィールドを抽出 (T, Ev, Type, Seq, PayloadSize)
                match = re.search(r'T=\s+([\d\.]+)\s+Ev=\s+(\w+)\s+Type=\s+(\w+)\s+ACK=\s+(\d+)\s+Seq=\s+(\d+)\s+PayloadSize=\s+(\d+)', line)
                if match:
                    data.append({
                        'T': float(match.group(1)),
                        'Ev': match.group(2),
                        'Type': match.group(3),
                        'Seq': int(match.group(5)),
                        'Size': int(match.group(6))
                    })
    except Exception as e:
        print(f"Error reading {filename}: {e}")
    return data

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 kawamura_anakyze_0203.py <CamN log> <CN log> [<RN1 log> <RN2 log> ...]")
        return

    filenames = sys.argv[1:]
    all_logs = {}
    for f in filenames:
        log = parse_log(f)
        if log:
            all_logs[f] = log

    if not all_logs:
        print("有効なログデータが見つかりませんでした。")
        return

    # 解析対象のタイプ
    target_types = ["VIDEO", "CONTROL"]

    for p_type in target_types:
        sources = []
        sinks = []
        
        # 各ノードの役割（Source/Sink）を判定
        for node, logs in all_logs.items():
            has_send = any(d['Type'] == p_type and d['Ev'] == 'Send' for d in logs)
            has_recv = any(d['Type'] == p_type and d['Ev'] == 'Recv' for d in logs)
            
            # 該当タイプを送信のみしている（またはリレーの起点）
            if has_send and not has_recv:
                sources.append(node)
            # 該当タイプを受信のみしている（またはリレーの終点）
            if has_recv and not has_send:
                sinks.append(node)
        
        # 役割が明確でない場合のフォールバック（最初の送信者と最後の受信者）
        if not sources or not sinks:
            potential_src = [n for n, l in all_logs.items() if any(d['Type'] == p_type and d['Ev'] == 'Send' for d in l)]
            potential_snk = [n for n, l in all_logs.items() if any(d['Type'] == p_type and d['Ev'] == 'Recv' for d in l)]
            if not potential_src or not potential_snk:
                continue
            src_node = potential_src[0]
            snk_node = potential_snk[-1]
        else:
            src_node = sources[0]
            snk_node = sinks[0]

        src_packets = [d for d in all_logs[src_node] if d['Type'] == p_type and d['Ev'] == 'Send']
        snk_packets = [d for d in all_logs[snk_node] if d['Type'] == p_type and d['Ev'] == 'Recv']

        if not src_packets or not snk_packets:
            continue

        # --- 1. パケットロス率 ---
        sent_seqs = {d['Seq'] for d in src_packets}
        recv_seqs = {d['Seq'] for d in snk_packets}
        # 重複を考慮せず、送信されたユニークなSeqがどれだけ到達したかで計算
        loss_count = len(sent_seqs - recv_seqs)
        loss_rate = (loss_count / len(sent_seqs)) * 100 if sent_seqs else 0

        # --- 2. スループット (Sink側での受信データ量 / 受信時間) ---
        snk_sorted = sorted(snk_packets, key=lambda x: x['T'])
        total_bits = sum(d['Size'] for d in snk_packets) * 8
        duration = snk_sorted[-1]['T'] - snk_sorted[0]['T']
        throughput_mbps = (total_bits / duration) / 1e6 if duration > 0 else 0

        # --- 3. End-to-End 遅延 (Source送信からSink受信までの平均時間) ---
        # 同じSeq番号を持つパケットの時刻差を計算
        src_times = {d['Seq']: d['T'] for d in src_packets}
        delays = []
        for d in snk_packets:
            if d['Seq'] in src_times:
                diff = d['T'] - src_times[d['Seq']]
                # 負の遅延は時刻同期のズレとして除外、またはそのまま平均
                delays.append(diff * 1000) # ms単位
        avg_delay = sum(delays) / len(delays) if delays else 0

        # 結果出力
        label = "映像データ (VIDEO)" if p_type == "VIDEO" else "制御用データ (CONTROL)"
        print(f"=== {label} ===")
        print(f"  送信ノード        : {src_node}")
        print(f"  受信ノード        : {snk_node}")
        print(f"  パケットロス率    : {loss_rate:.2f} %")
        print(f"  スループット      : {throughput_mbps:.4f} Mbps")
        print(f"  End-to-End 遅延   : {avg_delay:.4f} ms")
        print()

if __name__ == "__main__":
    main()
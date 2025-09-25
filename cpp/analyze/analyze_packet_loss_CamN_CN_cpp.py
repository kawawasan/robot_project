# C++版 パケロス率を計算

import sys
# import analyze_camn
# import analyze_cn
# import analyze_rn
import analyze_loss_delay_cpp

# 引数確認
if len(sys.argv) != 3:
    print(f"Usage: python3 {sys.argv[0]} CamN.log CN.log")
    sys.exit()

camn_file_name = sys.argv[1]
cn_file_name = sys.argv[2]
# rn1_file_name = sys.argv[3]
# rn2_file_name = sys.argv[4]


# recv_control_size, recv_control_num, send_video_size, send_video_num, control_throughput, camn_end_time = analyze_camn.analyze_camn(camn_file_name)

recv_video_size, recv_video_num, send_control_size, send_control_num, video_throughput, cn_end_time, recv_control_size, recv_control_num, send_video_size, send_video_num, control_throughput, camn_end_time, video_delay_max, control_delay_max, lost_ack_num = analyze_loss_delay_cpp.analyze_camn_cn(camn_file_name, cn_file_name)

# rn1_end_time = analyze_rn.analyze_rn(rn1_file_name)
# rn2_end_time = analyze_rn.analyze_rn(rn2_file_name)

# recv_video_size, recv_video_num, send_control_size, send_control_num, video_throughput, cn_end_time = analyze_cn.analyze_cn(cn_file_name)

# パケロス率を計算
control_loss_rate_size = (1 - recv_control_size / send_control_size) * 100
video_loss_rate_size = (1 - recv_video_size / send_video_size) * 100
control_loss_rate_num = (1 - recv_control_num / send_control_num) * 100
video_loss_rate_num = (1 - recv_video_num / send_video_num) * 100


print(f"CamN_end_time: {camn_end_time:.6f} s")
# print(f"RN1_end_time: {rn1_end_time:.6f} s")
# print(f"RN2_end_time: {rn2_end_time:.6f} s")
print(f"CN_end_time: {cn_end_time:.6f} s")

# if control_delay_max > 1e9 or video_delay_max > 1e9:
#     control_delay_max /= 1e9
#     video_delay_max /= 1e9
print(f"control_delay_max: {control_delay_max:.6f} s")
print(f"video_delay_max: {video_delay_max:.6f} s")
# print(f"Control_loss_rate_size: {control_loss_rate_size:.2f} %")
# print(f"Video_loss_rate_size: {video_loss_rate_size:.2f} %")
print(f"Control_loss_rate_num: {control_loss_rate_num:.2f} %")
print(f"Video_loss_rate_num: {video_loss_rate_num:.2f} %")
print(f"Lost_ack_num: {lost_ack_num}")
# スループット
# print(f"Control_throughput: {control_throughput:.6f} Mbps")
print(f"Video_throughput: {video_throughput:.6f} Mbps")

# 送受信サイズ
print(f"Send_control_num: {send_control_num} packets")
print(f"Recv_control_num: {recv_control_num} packets")
print(f"Send_video_num: {send_video_num} packets")
print(f"Recv_video_num: {recv_video_num} packets")
print(f"Send_control_size: {send_control_size:.6f} Bytes")
print(f"Recv_control_size: {recv_control_size:.6f} Bytes")
print(f"Send_video_size: {send_video_size:.6f} Bytes")
print(f"Recv_video_size: {recv_video_size:.6f} Bytes")


// UWB用で修正するよ 20260714~

// 制御ノード  同軸環境用
// 映像をtsファイルとして保存する
// 映像をストリーミング再生する．名前付きパイプを使用
// 制御情報を入力可能に

#include <iostream>
#include <thread>  // コンパイル時には-pthread
#include <algorithm>
#include <queue>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sstream>
#include <filesystem>
#include <csignal>
#include <sys/stat.h>
#include <atomic>
#include <cmath>
#include <fcntl.h>
#include <unistd.h> 

#include "../../include/header/bytequeue.hpp"  // 自作モジュール
#include "../../include/header/log.hpp"  // 自作モジュール
#include "../../include/header/packet.hpp"  // 自作モジュール

using std::cout ; // std::cout を cout と書ける
using std::endl ; // std::endl を endl と書ける
using hr_clock = std::chrono::high_resolution_clock;
using system_clock = std::chrono::system_clock;

// パケットタイプ 映像: 0, 制御情報: 1, ダミー: 2 31と30bit目
#define TYPE_VIDEO (uint32_t)0  // (00 << 30)
#define TYPE_CONTROL (uint32_t)(0b01 << 30)
#define TYPE_DUMMY (uint32_t)(0b10 << 30)
#define BUFFER_MAX 1500
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte(1500-UDPヘッダ-自作ヘッダ(8byte))．以前は1456，tsファイルは188byteのため，1316
#define CONTROL_SEQ_MAX (1 << 30)  // 30bitの最大値
#define VIDEO_SEQ_MAX 0xffffffff  // 32bitの最大値
#define DUMMY_SEQ_MAX 3  // ダミーパケット送信回数上限
#define FILE_NAME_PREFIX "videos/IPT_"  // 映像ファイル名プレフィックス

// グローバル変数
uint32_t g_control_seq = 0;  // 制御情報のシーケンス番号 0~2^30
uint32_t g_video_seq = 0;  // 映像シーケンス番号 0~2^32
uint32_t g_ack = -1;  // ack 0~2^30
ByteQueue g_video_bytequeue;  // 映像データキュー
ByteQueue g_command_bytequeue;  // 制御情報キュー
std::queue<std::vector<uint8_t>> g_video_queue;  // 映像データパケットキュー
std::mutex g_lock;
std::string g_video_file_name;  // 映像ファイル名

// ====================================================================
// ✨ [修正] 「キュー」ではなく「現在値レジスタ」に変更
// 理由: 送信トリガーはCamNからの下りパケット受信であり(receive_packet内)、
//       CN側は「その時点で最新の制御コマンド」を毎回乗せて返すのが正しい。
//       popして消費するキューにすると、別スレッド(旧ダミー生成)が同じ
//       キューに割り込んだ際に実コマンドが埋もれてしまう問題があった。
//       空文字列("")の間はまだ何も入力されていない状態を表し、
//       make_packet()側でDUMMYを送る判断に使う。
// ====================================================================
std::string g_current_command = "";  // 直近で計算された実コマンド（空文字=未入力）
uint32_t g_dummy_seq_cn = 0;          // 未入力時に送るDUMMYパケット用シーケンス

bool generate_input_end = false;  // コマンド生成終了フラグ
int generate_num = 0;  // 生成したコマンド数
std::atomic<int> g_send_num;  // 送信先のノード番号

// 関数の宣言
void generate_command_from_input(Log& log, std::chrono::high_resolution_clock::time_point start_time, const int node_num, const double communication_range, const double Vehicle_body_length, std::vector<std::vector<std::string>>& routing_table);


void signal_handler(int sig) {
    std::cout << "\n終了処理中..." << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    std::cout << "Program end" << std::endl;
    exit(0);
}

// MUCViS_CNクラス
class Mucvis_cn {
    hr_clock::time_point hr_start_time;
    int send_socket = socket(AF_INET, SOCK_DGRAM, 0);
    int recv_socket = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in my_addr;
    struct sockaddr_in up_addr;
    Log *log;
    double ipt_interval;
    int my_node_num;
    std::vector<std::vector<std::string>> routing_table;
    int send_node_before;

    std::string video_file_name;
    std::ofstream video_file;
    int pipe_fd;

    std::vector<uint8_t> video_data;
    std::size_t video_data_size;
    char buf[BUFFER_MAX];
    std::vector<uint8_t> send_payload;
    std::vector<uint8_t> recv_payload;

public:
    Mucvis_cn(std::string my_address, int my_port, std::string up_address, int up_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time, std::string video_file_name, int my_node_num, std::vector<std::vector<std::string>>& routing_table) {
        my_addr.sin_family = AF_INET;
        my_addr.sin_addr.s_addr = inet_addr(my_address.c_str());
        my_addr.sin_port = htons(my_port);
        up_addr.sin_family = AF_INET;
        up_addr.sin_addr.s_addr = inet_addr(up_address.c_str());
        up_addr.sin_port = htons(up_port);
        this->log = &log;
        this->ipt_interval = ipt_interval;
        this->hr_start_time = hr_start_time;
        this->video_file_name = video_file_name;
        this->my_node_num = my_node_num;
        this->routing_table = routing_table;
        this->send_node_before = g_send_num.load();

        video_data.reserve(MAX_VIDEO_SIZE);
        send_payload.reserve(MAX_VIDEO_SIZE + 8);
        recv_payload.reserve(MAX_VIDEO_SIZE + 8);

        std::string file_name_pass = FILE_NAME_PREFIX + video_file_name + "/" + video_file_name + ".ts";
        video_file.open(file_name_pass, std::ios::binary);
        if (!video_file) {
            std::cerr << "Failed to open video file: " << file_name_pass << std::endl;
            exit(EXIT_FAILURE);
        }

        if (!std::filesystem::exists("/tmp/ts_pipe")) {
            if (mkfifo("/tmp/ts_pipe", 0666) == -1) {
                std::cerr << "Failed to create named pipe: /tmp/ts_pipe" << std::endl;
                exit(EXIT_FAILURE);
            }
        }
        cout << "名前付きパイプ生成: /tmp/ts_pipe" << endl;
        
        this->pipe_fd = open("/tmp/ts_pipe", O_RDWR | O_NONBLOCK);
        if (this->pipe_fd == -1) {
            perror("Failed to open named pipe with O_NONBLOCK");
            exit(EXIT_FAILURE);
        } else {
            std::cout << "Named pipe opened successfully: /tmp/ts_pipe" << std::endl;
        }

        int recv_buffer_size = 1024 * 100;
        if (setsockopt(recv_socket, SOL_SOCKET, SO_RCVBUF, &recv_buffer_size, sizeof(recv_buffer_size)) == -1) {
            perror("setsockopt failed");
        }
    }

    // ====================================================================
    // ✨ [修正] g_current_command（現在値レジスタ）を参照する方式に変更
    // - 空文字列でなければ、その時点の最新コマンドをCONTROLとして毎回返す
    //   （popして消費しないので、下りパケットが来るたびに同じ内容を
    //    繰り返し送り続けられる＝設計で求められている継続送信と一致）
    // - 空文字列（＝まだユーザーが何も入力していない）の間はDUMMYを返し、
    //   CamN側との応答継続（ACK/シーケンスのやり取り）を絶やさない
    // ====================================================================
    Packet make_packet() {
        g_lock.lock();
        std::string control_command = g_current_command;
        g_lock.unlock();

        if (!control_command.empty()) {
            g_lock.lock();
            uint32_t sqe = g_control_seq;
            g_control_seq++;
            g_lock.unlock();

            Packet packet(TYPE_CONTROL, sqe, control_command);
            return packet;
        }

        g_lock.lock();
        uint32_t ack = g_ack;
        uint32_t seq = g_dummy_seq_cn;
        g_dummy_seq_cn++;
        g_lock.unlock();

        Packet packet(TYPE_DUMMY, ack, seq);
        return packet;
    }
    
    void send_packet() {
        Packet packet = make_packet();
        std::string packet_type = packet.get_type();
        if (packet_type == "UNKNOWN") return;

        send_payload = std::move(packet.get_payload());

        sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

        system_clock::time_point system_send_time = system_clock::now();
        hr_clock::time_point send_time = hr_clock::now();
        std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

        g_lock.lock();
        uint32_t ack = g_ack;
        log->write_camn_cn(duration, "Send", packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
        g_lock.unlock();
        
        int send_node = g_send_num.load();
        if (send_node_before > send_node) {
            send_node_before = send_node;
        }
        for (int i = send_node_before; i < my_node_num - 1; i++) {
            up_addr.sin_addr.s_addr = inet_addr(routing_table[i][1].c_str());
            sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

            std::string event = "Send_outside_num_" + std::to_string(i + 1);
            log->write_camn_cn(duration, event, packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
            send_node_before = send_node;
        }
        up_addr.sin_addr.s_addr = inet_addr(routing_table[send_node - 1][1].c_str());
    }

    void receive_packet() {
        buf[0] = '\0';
        uint32_t seq = 0;
        uint32_t ack = 0;
        uint32_t pre_ack;
        uint32_t pre_video_seq;

        int recv_size = recv(recv_socket, buf, sizeof(buf), 0);
        system_clock::time_point system_recv_time = system_clock::now();
        hr_clock::time_point recv_time = hr_clock::now();

        recv_payload.assign(buf, buf + recv_size);
        Packet packet(recv_payload);
        std::string packet_type = packet.get_type();

        if (packet_type == "VIDEO") {
            ack = packet.get_ack();
            seq = packet.get_videoSeq();

            g_lock.lock();
            g_video_queue.push(packet.get_videoData());
            pre_ack = g_ack;
            g_ack = ack;
            pre_video_seq = g_video_seq;
            g_video_seq = seq;
            g_lock.unlock();

            if (seq != pre_video_seq + 1 and seq != 0) {
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Video_seq_lost"
                    << " Pre_Seq= " << pre_video_seq 
                    << " Seq= " << seq;
                log->write(ss.str());
            }

            video_data = std::move(packet.get_videoData());
            video_data_size = video_data.size();

            ssize_t bytes_written = write(this->pipe_fd, video_data.data(), video_data_size);
            if (bytes_written == -1) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) {
                    // パイプ満杯時は破棄して続行
                } else {
                    perror("pipe write failed");
                }
            }
            video_file.write(reinterpret_cast<const char*>(video_data.data()), video_data_size);
            
            if (ack > pre_ack + 1) {
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Command_lost"
                    << " Pre_ACK= " << pre_ack 
                    << " ACK= " << ack;
                log->write(ss.str());
            }
        } else if (packet_type == "DUMMY") {
            ack = packet.get_ack();
            seq = packet.get_dummySeq();
            
            g_lock.lock();
            pre_ack = g_ack;
            g_ack = ack;
            g_lock.unlock();
            
            if (ack > pre_ack + 1) {
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Command_lost"
                    << " Pre_ACK= " << pre_ack 
                    << " ACK= " << ack;
                log->write(ss.str());
            }
        } else {
            ack = packet.get_ack();
        }
        
        log->write_camn_cn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, ack, seq, recv_size, system_recv_time);

        std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));

        if (packet_type == "VIDEO" or packet_type == "DUMMY") {
            send_packet();
        }
    }

    int start_receive() {
        if (bind(recv_socket, reinterpret_cast<sockaddr*>(&my_addr), sizeof(my_addr)) == -1) {
            std::cerr << "Failed to bind socket" << endl;
            close(recv_socket);
            return 1;
        }
        cout << "Waiting down packet" << endl;

        while (true) {
            receive_packet();
        }
        return 0;
    }

    ~Mucvis_cn() {
        close(send_socket);
        close(recv_socket);
        video_file.close();
        if (pipe_fd >= 0) close(pipe_fd); 
    }
};


int main(int argc, char* argv[]) {
    system_clock::time_point system_start_time = system_clock::now(); 
    hr_clock::time_point hr_start_time = hr_clock::now();

    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " [node_num] [log_name]" << endl;
        return 1;
    }
    std::ifstream ifs("../include/mucvis.conf");
    if (!ifs) {
        std::cerr << "Failed to open setting file: mucvis_setting.txt" << std::endl;
        return 1;
    }
    std::string parameter_list[] = {
        "node_num", "communication_range(m)", "Vehicle_body_length(m)", "IPT_interval(s)", "video_bit_rete(Mbps)", "time(s)", "up_port", "down_port"
    };
    std::string line;
    for(int i = 0; i < int(std::size(parameter_list)); i++) {
        if (std::getline(ifs, line)) {
            auto delimiter_pos = line.find('=');
            if (delimiter_pos != std::string::npos) {
                parameter_list[i] = line.substr(delimiter_pos + 1);
                }
            }
        }

    while(std::getline(ifs, line)) {
        if (line.find("node_type") != std::string::npos) break;
    }
    
    std::vector<std::vector<std::string>> routing_table;
    while(std::getline(ifs, line)) {
        if (line.empty()) break;
        auto delimiter_pos = line.find(' ');
        std::vector<std::string> row;
        while (delimiter_pos != std::string::npos) {
            row.push_back(line.substr(0, delimiter_pos));
            line = line.substr(delimiter_pos + 1);
            delimiter_pos = line.find(' ');
        }
        row.push_back(line);
        routing_table.push_back(row);
    }
    ifs.close();
    
    const int node_num = std::stoi(parameter_list[0]);
    const double communication_range = std::stod(parameter_list[1]);
    const double Vehicle_body_length = std::stod(parameter_list[2]);
    const double ipt_interval = std::stod(parameter_list[3]);
    const double video_bit_rate = std::stod(parameter_list[4]);
    const double generate_time_all = std::stod(parameter_list[5]);
    const int up_port = std::stoi(parameter_list[6]);
    const int down_port = std::stoi(parameter_list[7]);
    
    std::string video_file_name = argv[2];
    g_video_file_name = video_file_name;
    g_send_num.store(std::stoi(routing_table[node_num - 1][2]));
    
    const int my_node_num = node_num;
    std::string host = routing_table[my_node_num - 1][1];
    std::string up_address = routing_table[g_send_num.load() - 1][1];

    std::cout << "CN" << std::endl;
    std::cout << "node_num = " + std::to_string(node_num) << std::endl;
    std::cout << "communication_range = " + std::to_string(communication_range) + " m" << std::endl;
    std::cout << "Vehicle_body_length = " + std::to_string(Vehicle_body_length) + " m" << std::endl;
    std::cout << "IPT_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
    std::cout << "video_bit_rete = " + std::to_string(video_bit_rate) + " Mbps" << std::endl;
    std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
    std::cout << "up_port = " + std::to_string(up_port) << std::endl;
    std::cout << "down_port = " + std::to_string(down_port) << std::endl;
    std::cout << "video_file_name = " + video_file_name << std::endl;
    std::cout << "my_IP_address = " + host << std::endl;
    std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
    std::cout << "down_port = " + std::to_string(down_port) << std::endl;
    std::cout << "my_node_num = " + std::to_string(my_node_num) << std::endl;
    std::cout << "send_node = " + std::to_string(g_send_num.load()) << std::endl;
    std::cout << "routing_table:" << std::endl;
    for (const auto& row : routing_table) {
        for (const auto& item : row) {
            std::cout << item << " ";
        }
        std::cout << std::endl;
    }

    if (!std::filesystem::exists("videos")) std::filesystem::create_directory("videos");
    if (!std::filesystem::exists(FILE_NAME_PREFIX + video_file_name)) std::filesystem::create_directory(FILE_NAME_PREFIX + video_file_name);

    Log log("IPT", argv[2], system_start_time);
    log.write("CN");
    log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");

    Mucvis_cn mucvis_cn(host, down_port, up_address, up_port, log, ipt_interval, hr_start_time, video_file_name, node_num, std::ref(routing_table));

    std::thread receiver_thread(&Mucvis_cn::start_receive, &mucvis_cn);

    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    while (g_video_queue.size() == 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        continue;
    }
    
    // ✨ [修正] generate_command_fixed_interval（60byteダミー生成スレッド）は廃止。
    // 「未入力時にDUMMYを送る」役割はmake_packet()側に統合したので、
    // 起動すべきスレッドはユーザー入力を受け付ける1本だけになる。
    std::thread command_input_thread(generate_command_from_input, std::ref(log), hr_start_time, node_num, communication_range, Vehicle_body_length, std::ref(routing_table));

    // "exit"入力でgenerate_input_endが立てられ、input threadが終了する
    command_input_thread.join();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
    usleep(1000);

    mucvis_cn.~Mucvis_cn();

    std::cout << "Closing socket" << std::endl;
    std::cout << "Program end" << std::endl;
    return 0;
}


double read_uwb_distance_cn(int &nlos) {
    FILE *fp = fopen("/tmp/uwb_current_distance.txt", "r");
    if (fp == NULL) return -1.0;
    int dist_cm = 0;
    if (fscanf(fp, "%d,%d", &nlos, &dist_cm) == 2) {
        fclose(fp);
        return (double)dist_cm / 100.0;
    }
    fclose(fp);
    return -1.0;
}

// ========================================================================
// ✨ [修正] 任意のノード数 (robot_num) に対応できる完全汎用化アルゴリズム
// ========================================================================
void generate_command_from_input(Log& log, hr_clock::time_point hr_start_time, const int node_num, const double communication_range, const double Vehicle_body_length, std::vector<std::vector<std::string>>& routing_table) {
    hr_clock::time_point start_time = hr_start_time;
    int robot_num = node_num - 1; // CNを除いたロボットの総数

    const double R = communication_range;
    const double Lb = Vehicle_body_length;

    while (generate_input_end == false) {
        double t1 = R; double t2 = R + Lb * 2; double t3 = R * 2; double t4 = R * 2 + Lb; double t5 = R * 3;

        int nlos = 0;
        double current_m = read_uwb_distance_cn(nlos);

        std::cout << "\n========================================" << std::endl;
        if (current_m >= 0) {
            printf(" 📡 [UWB Monitor] 現在のロボット距離: %.2f m (NLos: %d)\n", current_m, nlos);
        } else {
            printf(" 📡 [UWB Monitor] UWBデータ取得待機中...\n");
        }
        printf(" Guidance: (1)L<=%.1f, (2)<=%.1f, (3)<=%.1f, (4)<=%.1f, (5)<=%.1f\n", t1, t2, t3, t4, t5);
        std::cout << "Enter target L [m]: ";

        std::string input;
        std::getline(std::cin, input);
        if (input == "exit") {
            generate_input_end = true;  // このスレッドがjoin対象になったのでここで終了フラグを立てる
            return;
        }
        if (input.empty()) continue;

        try {
            double L = std::stod(input);
            int k = std::ceil(L / R);
            k = std::clamp(k, 1, robot_num); // 要求ホップ数を台数内に収める

            // ----------------------------------------------------
            // 1. 各ロボットの位置 P を動的計算
            // P[1] がCNの目の前のRN、P[robot_num] が先頭のCamN
            // ----------------------------------------------------
            std::vector<double> P(robot_num + 1, 0.0);
            P[robot_num] = L; 
            for (int i = robot_num - 1; i >= 1; i--) {
                P[i] = std::max(i * Lb, P[i + 1] - R);
            }

            // ----------------------------------------------------
            // 2. 隙間 (Gap) の算出
            // gaps[0] = CamNの隙間, gaps[robot_num-1] = CN直前のRNの隙間
            // ----------------------------------------------------
            std::vector<double> gaps(robot_num, 0.0);
            for (int i = 0; i < robot_num; i++) {
                double p_front = P[robot_num - i];
                double p_back = (i == robot_num - 1) ? 0.0 : P[robot_num - i - 1];
                gaps[i] = p_front - p_back - Lb;
            }

            // ----------------------------------------------------
            // 3. ルーティングの動的更新
            // ----------------------------------------------------
            g_send_num.store(k); // CtlN自身の送信先
            
            // 安全対策：ルーティングテーブルの列数を確保 (node, IP, up, down)
            for (size_t i = 0; i < routing_table.size(); i++) {
                if (routing_table[i].size() <= 3) {
                    routing_table[i].resize(4, "0");
                }
            }
            
            // 全ロボット (Index 1 〜 robot_num) のルーティングを書き換える
            for (int i = 1; i <= robot_num; i++) {
                if (routing_table.size() < (size_t)i) break; // 設定ファイルの行数不足エラー防止
                
                int table_idx = i - 1; // routing_table は 0-origin
                
                // --- 下りパス (Downlink): 映像・ACKがCNへ戻る道 ---
                // ホップ圏内(k番目以降)にいるなら直接CNへ。遠いなら隣のRNへ渡す
                if (i >= k) {
                    routing_table[table_idx][3] = std::to_string(node_num);
                } else {
                    routing_table[table_idx][3] = std::to_string(i + 1);
                }

                // --- 上りパス (Uplink): 制御コマンドがCamNへ向かう道 ---
                // ルート上のノードならCamN方向(i-1)へ。ルート外なら送信停止(0)
                if (i == 1) {
                    // CamN は最終宛先なので転送しない
                } else if (i <= k) {
                    routing_table[table_idx][2] = std::to_string(i - 1);
                } else {
                    routing_table[table_idx][2] = "0"; 
                }
            }

            // ----------------------------------------------------
            // 4. コマンド文字列生成
            // ----------------------------------------------------
            std::string final_command;
            for (int i = 0; i < robot_num; i++) {
                int cm = static_cast<int>(std::round(gaps[i] * 100));
                if (i == 0) {
                    final_command += std::to_string(cm) + " " + routing_table[0][3] + ",";
                } else {
                    final_command += std::to_string(cm) + " " + routing_table[i][2] + " " + routing_table[i][3] + ",";
                }
            }
            final_command.pop_back();

            // 5. 送信（現在値レジスタを更新するだけ。実際の送信はmake_packet()が
            //    下りパケット受信のたびに行う。popで消費されないので、
            //    次にLが入力されるまでこの値を送り続けられる）
            g_lock.lock();
            g_current_command = final_command;
            g_lock.unlock();

            log.write_generate(std::chrono::duration<double>(hr_clock::now() - start_time), "Command", generate_num++, final_command.size(), final_command);
            printf(">> Target: %.2fm (%d-hop), Command: %s\n", L, k, final_command.c_str());

        } catch (...) { continue; }
    }
}

// ========================================================================
// ✨ [廃止] generate_command_fixed_interval
// 60byteの固定ダミー文字列を100msごとにg_command_queueへ積み続けていた関数。
// generate_command_from_input が push する実コマンドと同じキューを取り合い、
// 「入力した距離コマンドがダミーに埋もれてCamNに届かない/上書きされる」
// バグの直接の原因だったため廃止。
// 「未入力時にDUMMYを送り続ける」という本来の役割は、
// Mucvis_cn::make_packet() が g_current_command の空/非空を見て
// CONTROL/DUMMYを都度生成する形に統合した。
// ========================================================================
// void generate_command_fixed_interval(double generate_time_all, Log& log, hr_clock::time_point hr_start_time) {
//     double generate_command_interval = 0.1;
//     std::string command_data = "The control command is generated so that it is 60 bytes long";
//     std::chrono::duration<double> duration;
//     std::chrono::duration<double> log_time;
//
//     std::cout << "Start generate command data" << std::endl;
//     hr_clock::time_point generate_time_now;
//     hr_clock::time_point start_time = hr_start_time;
//
//     while (true) {
//         generate_time_now = hr_clock::now();
//         duration = std::chrono::duration<double>(generate_time_now - start_time);
//         if (duration.count() >= generate_time_all) {
//             std::this_thread::sleep_for(std::chrono::milliseconds(100));
//             return;
//         }
//
//         g_lock.lock();
//         g_command_queue.push(command_data);
//         g_lock.unlock();
//
//         log_time = std::chrono::duration<double>(generate_time_now - start_time);
//         log.write_generate(log_time, "Command", generate_num, command_data.size());
//         generate_num++;
//
//         std::this_thread::sleep_for(std::chrono::milliseconds((int)(generate_command_interval*1000)));
//     }
// }
// // UWB用で修正するよ 20260710~

// // 制御ノード  同軸環境用
// // 映像をtsファイルとして保存する
// // 映像をストリーミング再生する．名前付きパイプを使用
// // 制御情報を入力可能に

// #include <iostream>
// #include <thread>  // コンパイル時には-pthread
// #include <algorithm>
// #include <queue>
// #include <sys/socket.h>
// #include <netinet/in.h>
// #include <arpa/inet.h>
// #include <unistd.h>
// #include <sstream>
// #include <filesystem>
// #include <csignal>
// #include <sys/stat.h>
// #include <atomic>
// #include <cmath>
// #include <fcntl.h>
// #include <unistd.h> 

// #include "../../include/header/bytequeue.hpp"  // 自作モジュール
// #include "../../include/header/log.hpp"  // 自作モジュール
// #include "../../include/header/packet.hpp"  // 自作モジュール

// using std::cout ; // std::cout を cout と書ける
// using std::endl ; // std::endl を endl と書ける
// using hr_clock = std::chrono::high_resolution_clock;
// using system_clock = std::chrono::system_clock;

// // パケットタイプ 映像: 0, 制御情報: 1, ダミー: 2 31と30bit目
// #define TYPE_VIDEO (uint32_t)0  // (00 << 30)
// #define TYPE_CONTROL (uint32_t)(0b01 << 30)
// #define TYPE_DUMMY (uint32_t)(0b10 << 30)
// #define BUFFER_MAX 1500
// #define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte(1500-UDPヘッダ-自作ヘッダ(8byte))．以前は1456，tsファイルは188byteのため，1316
// #define CONTROL_SEQ_MAX (1 << 30)  // 30bitの最大値
// #define VIDEO_SEQ_MAX 0xffffffff  // 32bitの最大値
// #define DUMMY_SEQ_MAX 3  // ダミーパケット送信回数上限
// #define FILE_NAME_PREFIX "videos/IPT_"  // 映像ファイル名プレフィックス

// // グローバル変数
// uint32_t g_control_seq = 0;  // 制御情報のシーケンス番号 0~2^30
// uint32_t g_video_seq = 0;  // 映像シーケンス番号 0~2^32
// uint32_t g_ack = -1;  // ack 0~2^30
// ByteQueue g_video_bytequeue;  // 映像データキュー
// ByteQueue g_command_bytequeue;  // 制御情報キュー
// std::queue<std::vector<uint8_t>> g_video_queue;  // 映像データパケットキュー
// std::queue<std::string> g_command_queue;  // 制御コマンドキュー
// std::mutex g_lock;
// std::string g_video_file_name;  // 映像ファイル名

// // int g_write_size = 0;  // 映像データ書き込みサイズ
// // int g_recv_size = 0;  // 映像データ受信サイズ

// // const double generate_time_all = 600.0;  // コマンド生成時間 [s]
// bool generate_input_end = false;  // コマンド生成終了フラグ
// int generate_num = 0;  // 生成したコマンド数
// std::atomic<int> g_send_num;  // 送信先のノード番号

// // 関数の宣言
// void generate_command_from_input(Log& log, std::chrono::high_resolution_clock::time_point start_time, const int node_num, const double communication_range, const double Vehicle_body_length, std::vector<std::vector<std::string>>& routing_table);

// void generate_command_fixed_interval(double generate_time_all, Log& log, std::chrono::high_resolution_clock::time_point start_time);
// // void ffmpeg_ts_mp4();


// void signal_handler(int sig) {
//     std::cout << "\n終了処理中..." << std::endl;

//     // 映像ファイルをmp4に変換
//     // ffmpeg_ts_mp4();

//     std::this_thread::sleep_for(std::chrono::milliseconds(1));
//     std::cout << "Program end" << std::endl;

//     exit(0);
// }

// // MUCViS_CNクラス
// class Mucvis_cn {
//     hr_clock::time_point hr_start_time;  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()
//     int send_socket = socket(AF_INET, SOCK_DGRAM, 0);
//     int recv_socket = socket(AF_INET, SOCK_DGRAM, 0);
//     struct sockaddr_in my_addr;
//     struct sockaddr_in up_addr;
//     Log *log;
//     double ipt_interval;
//     int my_node_num;
//     std::vector<std::vector<std::string>> routing_table;
//     int send_node_before;  // 直前に送信したノード

//     std::string video_file_name;
//     std::ofstream video_file;
//     // 受け取った映像をストリーミング再生するための名前付きパイプを定義
//     // std::ofstream pipe_file; 0512河村
//     int pipe_fd;

//     std::vector<uint8_t> video_data;
//     std::size_t video_data_size;
//     char buf[BUFFER_MAX];
//     std::vector<uint8_t> send_payload;
//     std::vector<uint8_t> recv_payload;

// public:
//     Mucvis_cn(std::string my_address, int my_port, std::string up_address, int up_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time, std::string video_file_name, int my_node_num, std::vector<std::vector<std::string>>& routing_table) {
//         my_addr.sin_family = AF_INET;
//         my_addr.sin_addr.s_addr = inet_addr(my_address.c_str());
//         my_addr.sin_port = htons(my_port);
//         up_addr.sin_family = AF_INET;
//         up_addr.sin_addr.s_addr = inet_addr(up_address.c_str());
//         up_addr.sin_port = htons(up_port);
//         this->log = &log;
//         this->ipt_interval = ipt_interval;
//         this->hr_start_time = hr_start_time;
//         this->video_file_name = video_file_name;
//         this->my_node_num = my_node_num;
//         this->routing_table = routing_table;
//         this->send_node_before = g_send_num.load();

//         video_data.reserve(MAX_VIDEO_SIZE);
//         send_payload.reserve(MAX_VIDEO_SIZE + 8);  // ヘッダ8byte + 映像データ最大1464byte
//         recv_payload.reserve(MAX_VIDEO_SIZE + 8);  // ヘッダ8byte + 映像データ最大1464byte

//         // 映像ファイルを開く
//         std::string file_name_pass = FILE_NAME_PREFIX + video_file_name + "/" + video_file_name + ".ts";
//         video_file.open(file_name_pass, std::ios::binary);
//         if (!video_file) {
//             std::cerr << "Failed to open video file: " << file_name_pass << std::endl;
//             exit(EXIT_FAILURE);
//         }

//         // 名前付きパイプを作成
//         if (!std::filesystem::exists("/tmp/ts_pipe")) {
//             if (mkfifo("/tmp/ts_pipe", 0666) == -1) {
//                 std::cerr << "Failed to create named pipe: /tmp/ts_pipe" << std::endl;
//                 exit(EXIT_FAILURE);
//             }
//         }
//         cout << "名前付きパイプ生成: /tmp/ts_pipe" << endl;
//         // --- 追加 ---kawamura
//         // ※必ずファイルの先頭に #include <fcntl.h> と #include <unistd.h> を入れてください
//         this->pipe_fd = open("/tmp/ts_pipe", O_RDWR | O_NONBLOCK);
//         if (this->pipe_fd == -1) {
//             perror("Failed to open named pipe with O_NONBLOCK");
//             exit(EXIT_FAILURE);
        
//         // pipe_file.open("/tmp/ts_pipe", std::ios::binary);
//         // if (!pipe_file) {
//         //     std::cerr << "Failed to open named pipe: /tmp/ts_pipe" << std::endl;
//         //     exit(EXIT_FAILURE);
//         } else {
//             std::cout << "Named pipe opened successfully: /tmp/ts_pipe" << std::endl;
//         }

//         // 受信ソケットのバッファサイズを設定
//         int recv_buffer_size = 1024 * 100;  // 1MB
//         if (setsockopt(recv_socket, SOL_SOCKET, SO_RCVBUF, &recv_buffer_size, sizeof(recv_buffer_size)) == -1) {
//             perror("setsockopt failed");
//         }
//     }

//     // パケット生成
//     Packet make_packet() {
//         uint32_t packet_type = (0b11 << 30);  // UNKNOWN
//         static uint32_t unknown_seq = 0;
//         g_lock.lock();
//         int g_command_queue_size = g_command_queue.size();
//         g_lock.unlock();

//         if (g_command_queue_size != 0) {
//             packet_type = TYPE_CONTROL;
//         }

//         if (packet_type == TYPE_CONTROL) {
//             g_lock.lock();
//             std::string control_command = g_command_queue.front();
//             g_command_queue.pop();
//             uint32_t sqe = g_control_seq;
//             g_control_seq++;
//             g_lock.unlock();

//             // パケット生成
//             Packet packet(packet_type, sqe, control_command);

//             return packet;
//         }
//         Packet packet(packet_type, 0, unknown_seq++);  // UNKNOWN packet
//         return packet;
//     }
    
//     // void send_packet() {
//     //     // パケット生成
//     //     Packet packet = make_packet();

//     //     std::string packet_type = packet.get_type();
//     //     if (packet_type == "UNKNOWN") {
//     //         return;
//     //     }

//     //     send_payload = std::move(packet.get_payload());  // ムーブで効率的に転送

//     //     // --- ログ・時間計測の準備 ---
//     //     system_clock::time_point system_send_time = system_clock::now();
//     //     hr_clock::time_point send_time = hr_clock::now();
//     //     std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

//     //     g_lock.lock();
//     //     uint32_t ack = g_ack;
//     //     g_lock.unlock();

//     //     // 現在のホップ数（正規ルートの入り口）を取得
//     //     int send_node = g_send_num.load();
        
//     //     // --- 1. 中継外のノード（お休み中）に制御情報を送信する ---
//     //     // send_node_before は不要。現在の send_node からスタートするだけで完璧に判定可能。
//     //     for (int i = send_node; i < my_node_num - 1; i++) {
//     //         up_addr.sin_addr.s_addr = inet_addr(routing_table[i][1].c_str());
//     //         sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

//     //         // お休みノードへの送信ログ
//     //         std::string event = "Send_outside_num_" + std::to_string(i + 1);
//     //         log->write_camn_cn(duration, event, packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
//     //     }

//     //     // --- 2. 本命（正規の中継ルートの入り口）に送信する ---
//     //     up_addr.sin_addr.s_addr = inet_addr(routing_table[send_node - 1][1].c_str());
//     //     sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));
        
//     //     // 本命への送信ログ
//     //     log->write_camn_cn(duration, "Send", packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
//     // }

//     void send_packet() {
//         // パケット生成
//         Packet packet = make_packet();

//         std::string packet_type = packet.get_type();
//         if (packet_type == "UNKNOWN") {
//             return;
//         }

//         // std::vector<uint8_t> send_payload = packet.get_payload();
//         // send_payload.clear();
//         // send_payload = packet.get_payload();
//         send_payload = std::move(packet.get_payload());  // ムーブで効率的に転送

//         // 上りへ送信
//         sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

//         system_clock::time_point system_send_time = system_clock::now();
//         hr_clock::time_point send_time = hr_clock::now();
//         std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

//         g_lock.lock();
//         uint32_t ack = g_ack;

//         // ログに書き込む
//         log->write_camn_cn(duration, "Send", packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
//         g_lock.unlock();

        
//         // 中継外の送信先を決める
//         int send_node = g_send_num.load();
//         if (send_node_before > send_node) {
//             send_node_before = send_node;
//         }
//         // 中継外のノードに制御情報を送信する
//         for (int i = send_node_before; i < my_node_num - 1; i++) {
//             up_addr.sin_addr.s_addr = inet_addr(routing_table[i][1].c_str());  // 送信先アドレスを更新
            
//             sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));

//             // ログに書き込む
//             std::string event = "Send_outside_num_" + std::to_string(i + 1);
//             log->write_camn_cn(duration, event, packet_type, ack, packet.get_commandSeq(), send_payload.size(), system_send_time);
//             send_node_before = send_node;
//         }

//         up_addr.sin_addr.s_addr = inet_addr(routing_table[send_node - 1][1].c_str());  // 送信先アドレスを更新
//         // up_addr.sin_port = htons(std::stoi(routing_table[send_node - 1][1].c_str()));  // ローカルのため，ポート番号を変更
//         // sendto(send_socket, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));変更　河村

//     }

//     void receive_packet() {
//         // char buf[BUFFER_MAX];
//         buf[0] = '\0';  // バッファを初期化
//         uint32_t seq = 0;
//         uint32_t ack = 0;
//         uint32_t pre_ack;
//         uint32_t pre_video_seq;

//         int recv_size = recv(recv_socket, buf, sizeof(buf), 0);

//         system_clock::time_point system_recv_time = system_clock::now();
//         hr_clock::time_point recv_time = hr_clock::now();
//         // recv_payload(buf, buf + recv_size);
//         // recv_payload.clear();
//         // recv_payload = std::vector<uint8_t>(buf, buf + recv_size);
//         recv_payload.assign(buf, buf + recv_size);
//         // std::vector<uint8_t> payload(buf, buf + recv_size);
//         Packet packet(recv_payload);
//         std::string packet_type = packet.get_type();

//         if (packet_type == "VIDEO") {
//             ack = packet.get_ack();
//             seq = packet.get_videoSeq();

//             g_lock.lock();
//             g_video_queue.push(packet.get_videoData());
//             pre_ack = g_ack;
//             g_ack = ack;

//             pre_video_seq = g_video_seq;
//             g_video_seq = seq;
//             g_lock.unlock();

//             // video_seqが連番でないときは書き込まず終了
//             if (seq != pre_video_seq + 1 and seq != 0) {
//                 std::stringstream ss;
//                 ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
//                     << " Ev= Video_seq_lost"
//                     << " Pre_Seq= " << pre_video_seq 
//                     << " Seq= " << seq;
//                 log->write(ss.str());
//                 // 連番でない場合は異常終了
//                 // exit(EXIT_FAILURE);
//             }

//             // パケットから映像データをサイズを取得
//             // std::vector<uint8_t> video_data = packet.get_videoData();
//             // std::size_t video_data_size = video_data.size();
//             // video_data.clear();  // 映像データをクリア
//             // video_data = packet.get_videoData();
//             video_data = std::move(packet.get_videoData());  // 映像データをムーブ
//             video_data_size = video_data.size();
//             // cout << "映像データ受信サイズ: " << video_data_size << " byte" << endl;

//             // 映像データを名前付きパイプに渡す．ストリーミング再生用
//             // pipe_file.write(reinterpret_cast<const char*>(packet.get_videoData().data()), packet.get_videoData().size());
//             // pipe_file.write(reinterpret_cast<const char*>(video_data.data()), video_data_size);河村削除0512

//             // --- 追加（非ブロッキングで強行突破する 河村
//             ssize_t bytes_written = write(this->pipe_fd, video_data.data(), video_data_size);
//             if (bytes_written == -1) {
//                 // EAGAIN または EWOULDBLOCK は「パイプが満杯」という意味
//                 if (errno == EAGAIN || errno == EWOULDBLOCK) {
//                     // 【超重要】再生側（Mac）が詰まっているので、このパケットは諦めて捨てる！
//                     // 何もせずに次へ進むことで、CNのプログラムは「絶対に」止まらなくなります。
//                 } else {
//                     // 本当のエラー（パイプが壊れた等）
//                     perror("pipe write failed");
//                 }
//             }
//             // --------------------------------------------------------

//             //
//             // pipe_file.flush();  
//             // 映像データをファイルに書き込む
//             // video_file.write(reinterpret_cast<const char*>(packet.get_videoData().data()), packet.get_videoData().size());
//             video_file.write(reinterpret_cast<const char*>(video_data.data()), video_data_size);
//             // video_file.flush();
//             // cout << "映像データ書き込みサイズ: " << packet.get_videoData().size() << " byte" << endl;
//             // g_write_size += packet.get_videoData().size();
//             // g_recv_size += recv_size;
            
//             // コマンドパケットのロストをackで検知
//             if (ack > pre_ack + 1) {
//                 std::stringstream ss;
//                 ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
//                     << " Ev= Command_lost"
//                     << " Pre_ACK= " << pre_ack 
//                     << " ACK= " << ack;
//                 log->write(ss.str());
//             }
//         } else if (packet_type == "DUMMY") {
//             ack = packet.get_ack();
//             seq = packet.get_dummySeq();
            
//             g_lock.lock();
//             pre_ack = g_ack;
//             g_ack = ack;
//             g_lock.unlock();
            
//             // コマンドパケットのロストをackで検知
//             if (ack > pre_ack + 1) {
//                 std::stringstream ss;
//                 ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
//                     << " Ev= Command_lost"
//                     << " Pre_ACK= " << pre_ack 
//                     << " ACK= " << ack;
//                 log->write(ss.str());
//             }

//             // 送信間隔 I / 3 待機
//             // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
//         } else {  // CONTROL
//             ack = packet.get_ack();
//             std::string command = packet.get_command();

//             // 送信間隔 I / 3 待機
//             // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
//         }
//         // ログ出力
//         log->write_camn_cn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, ack, seq, recv_size, system_recv_time);

//         // 送信間隔 I / 3 待機
//         // if (packet_type == "DUMMY" or packet_type == "CONTROL") {
//             std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
//         // }

//         // パケット送信
//         if (packet_type == "VIDEO" or packet_type == "DUMMY") {
//             send_packet();
//         }
//     }

//     int start_receive() {
//         if (bind(recv_socket, reinterpret_cast<sockaddr*>(&my_addr), sizeof(my_addr)) == -1) {
//             std::cerr << "Failed to bind socket" << endl;
//             close(recv_socket);
//             return 1;
//         }
//         cout << "Waiting down packet" << endl;

//         while (true) {
//             receive_packet();
//         }

//         return 0;
//     }

//     ~Mucvis_cn() {
//         close(send_socket);
//         close(recv_socket);
//         video_file.close();
//         // pipe_file.close();削除　河村0512
//         if (pipe_fd >= 0) {
//             close(pipe_fd); 
//         }

//         // cout << "受信映像データサイズ: " << g_recv_size << " byte" << endl;
//         // cout << "書き込み映像データサイズ: " << g_write_size << " byte" << endl;
//     }
// };


// int main(int argc, char* argv[]) {
//     system_clock::time_point system_start_time = system_clock::now();  // システム起動時刻 ノード間時刻同期用
//     hr_clock::time_point hr_start_time = hr_clock::now();  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()

//     // 引数でパラメータ指定
//     // 引数チェック
//     // if (argc != 5) {
//     //     std::cerr << "Usage: " << argv[0] << " [My IP Address] [Send IP Address] [IPT interval(s)] [log_name]" << endl;
//     //     return 1;
//     // }

//     // std::string host = argv[1];  // 自身のIPアドレス
//     // std::string up_address = argv[2];  // 宛先IPアドレス
//     // int down_port = 60202;  // ポート番号60202: 下り用, ローカル: 60204: 3ノード, 60202: 2ノード(1対1)
//     // int up_port = 60201;  // ポート番号60201: 上り用, ローカル: 60203: 3ノード, 60201: 2ノード(1対1)
//     // double ipt_interval = std::stod(argv[3]);  // 送信間隔 1msぐらい?
//     // std::string video_file_name = argv[4];  // 映像ファイル名
//     // g_video_file_name = video_file_name;

//     // const int node_num = 4;
//     // const double communication_range = 1;  // 通信可能距離[m]
//     // const double Vehicle_body_length = 0.1;  // 車両長[m]
//     // node_type IP default_up default_down
//     // std::vector<std::vector<std::string>> routing_table = {
//     //     {"camn", "192.168.20.21", "0", "2"},
//     //     {"rn", "192.168.20.22", "1", "3"},
//     //     {"rn", "192.168.20.23", "2", "4"}, 
//     //     {"cn", "192.168.20.24", "2", "0"}
//     // };


//     // 設定ファイルからパラメータ読み込み
//     // 引数チェック
//     if (argc != 3) {
//         std::cerr << "Usage: " << argv[0] << " [node_num] [log_name]" << endl;
//         return 1;
//     }
//     // ファイルオープン
//     std::ifstream ifs("../include/mucvis.conf");
//     if (!ifs) {
//         std::cerr << "Failed to open setting file: mucvis_setting.txt" << std::endl;
//         return 1;
//     }
//     // パラメータ読み込み
//     std::string parameter_list[] = {
//         "node_num", "communication_range(m)", "Vehicle_body_length(m)", "IPT_interval(s)", "video_bit_rete(Mbps)", "time(s)", "up_port", "down_port"
//     };
//     std::string line;
//     for(int i = 0; i < int(std::size(parameter_list)); i++) {
//         if (std::getline(ifs, line)) {
//             auto delimiter_pos = line.find('=');
//             if (delimiter_pos != std::string::npos) {
//                 parameter_list[i] = line.substr(delimiter_pos + 1);
//                 }
//             }
//         }

//     // lineにnode_typeがあるまで読み飛ばす
//     while(std::getline(ifs, line)) {
//         if (line.find("node_type") != std::string::npos) {
//             break;
//         }
//     }
//     // 初期ルーティングテーブル読み込み
//     std::vector<std::vector<std::string>> routing_table;
//     while(std::getline(ifs, line)) {
//         if (line.empty()) {
//             break;
//         }
//         auto delimiter_pos = line.find(' ');
//         std::vector<std::string> row;
//         while (delimiter_pos != std::string::npos) {
//             row.push_back(line.substr(0, delimiter_pos));
//             line = line.substr(delimiter_pos + 1);
//             delimiter_pos = line.find(' ');
//         }
//         row.push_back(line);
//         routing_table.push_back(row);
//         }
//     ifs.close();
    
//     const int node_num = std::stoi(parameter_list[0]);
//     const double communication_range = std::stod(parameter_list[1]);  // 通信可能距離[m]
//     const double Vehicle_body_length = std::stod(parameter_list[2]);  // 車両長[m]
//     const double ipt_interval = std::stod(parameter_list[3]);  // 送信間隔 1msぐらい?
//     const double video_bit_rate = std::stod(parameter_list[4]);  // 映像ビットレート [Mbps]
//     const double generate_time_all = std::stod(parameter_list[5]);  // コマンド生成時間 [s]
//     const int up_port = std::stoi(parameter_list[6]);  // ポート番号
//     const int down_port = std::stoi(parameter_list[7]);  // ポート番号
//     std::string video_file_name = argv[2];  // 映像ファイル名
//     g_video_file_name = video_file_name;
//     g_send_num.store(std::stoi(routing_table[node_num - 1][2]));
//     const int my_node_num = node_num;
//     std::string host = routing_table[my_node_num - 1][1];  // 自身のIPアドレス
//     std::string up_address = routing_table[g_send_num.load() - 1][1];  // 宛先IPアドレス
//     // int send_socket = socket(AF_INET, SOCK_DGRAM, 0);

//     // 上のパラメータを表示
//     std::cout << "CN" << std::endl;
//     std::cout << "node_num = " + std::to_string(node_num) << std::endl;
//     std::cout << "communication_range = " + std::to_string(communication_range) + " m" << std::endl;
//     std::cout << "Vehicle_body_length = " + std::to_string(Vehicle_body_length) + " m" << std::endl;
//     std::cout << "IPT_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
//     std::cout << "video_bit_rete = " + std::to_string(video_bit_rate) + " Mbps" << std::endl;
//     std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
//     std::cout << "up_port = " + std::to_string(up_port) << std::endl;
//     std::cout << "down_port = " + std::to_string(down_port) << std::endl;
//     std::cout << "video_file_name = " + video_file_name << std::endl;
//     std::cout << "my_IP_address = " + host << std::endl;
//     std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
//     std::cout << "down_port = " + std::to_string(down_port) << std::endl;
//     std::cout << "my_node_num = " + std::to_string(my_node_num) << std::endl;
//     std::cout << "send_node = " + std::to_string(g_send_num.load()) << std::endl;
//     std::cout << "routing_table:" << std::endl;
//     for (const auto& row : routing_table) {
//         for (const auto& item : row) {
//             std::cout << item << " ";
//         }
//         std::cout << std::endl;
//     }

//     // ディレクトリが存在しない場合は作成
//     if (!std::filesystem::exists("videos")) {
//         std::filesystem::create_directory("videos");
//     }
//     if (!std::filesystem::exists(FILE_NAME_PREFIX + video_file_name)) {
//         std::filesystem::create_directory(FILE_NAME_PREFIX + video_file_name);
//     }

//     // ログファイル作成
//     // Log log("IPT", argv[4], system_start_time);
//     Log log("IPT", argv[2], system_start_time);
//     log.write("CN");
//     log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");

//     // 標準出力
//     // std::cout << "CN" << std::endl;
//     // std::cout << "my_IP_address = " + host << std::endl;
//     // std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
//     // std::cout << "ipt_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
//     // std::cout << "generate_time_all = " + std::to_string(generate_time_all) + " s" << std::endl;
//     // int send_socket = socket(AF_INET, SOCK_DGRAM, 0);

//     // クラスのインスタンス化
//     Mucvis_cn mucvis_cn(host, down_port, up_address, up_port, log, ipt_interval, hr_start_time, video_file_name, node_num, std::ref(routing_table));  // 実験環境用
//     // Mucvis_cn mucvis_cn(host, 60204, up_address, 60203, log, start_time);  // ローカル環境用(ポートで振り分け)

//     std::thread receiver_thread(&Mucvis_cn::start_receive, &mucvis_cn);

//     // シグナルハンドラ設定
//     signal(SIGINT, signal_handler);
//     signal(SIGTERM, signal_handler);

//     while (g_video_queue.size() == 0) {
//         std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 0.001秒待機
//         continue;
//     }  // 映像データを受信したらコマンド生成スレッドを開始
//     std::thread command_generate_thread(generate_command_fixed_interval, generate_time_all, std::ref(log), hr_start_time);
//     std::thread command_input_thread(generate_command_from_input, std::ref(log), hr_start_time, node_num, communication_range, Vehicle_body_length, std::ref(routing_table));

//     // コマンド生成終了まで待機
//     command_generate_thread.join();
//     std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 0.001秒待機
//     generate_input_end = true;  // コマンド生成終了フラグを立てる
//     usleep(1000);  // 0.001秒待機

//     mucvis_cn.~Mucvis_cn();
//     // ffmpeg_ts_mp4();

//     std::cout << "Closing socket" << std::endl;
//     // close(send_socket);
//     std::cout << "Program end" << std::endl;
//     return 0;
// }

// // ---------------------------------------------------------
// // ✨ 追加: CtlN側でUWBの現在距離をファイルから読み取るヘルパー関数
// // ---------------------------------------------------------
// double read_uwb_distance_cn(int &nlos) {
//     FILE *fp = fopen("/tmp/uwb_current_distance.txt", "r");
//     if (fp == NULL) return -1.0;
//     int dist_cm = 0;
//     if (fscanf(fp, "%d,%d", &nlos, &dist_cm) == 2) {
//         fclose(fp);
//         return (double)dist_cm / 100.0;
//     }
//     fclose(fp);
//     return -1.0;
// }

// // 制御コマンドを標準入力から受け取り，ルーティングを計算し制御コマンドを作成，キューに格納する関数
// void generate_command_from_input(Log& log, hr_clock::time_point hr_start_time, const int node_num, const double communication_range, const double Vehicle_body_length, std::vector<std::vector<std::string>>& routing_table) {
//     static std::mutex lock;
//     hr_clock::time_point start_time = hr_start_time;
//     int robot_num = node_num - 1; 

//     const double R = communication_range;
//     const double Lb = Vehicle_body_length;

//     while (generate_input_end == false) {
//         // --- フェーズ表示 ---
//         double t1 = R; double t2 = R + Lb * 2; double t3 = R * 2; double t4 = R * 2 + Lb; double t5 = R * 3;

//         // ✨ 追加: UWBの現在距離を読み取る
//         int nlos = 0;
//         double current_m = read_uwb_distance_cn(nlos);

//         std::cout << "\n========================================" << std::endl;

//         // ✨ 追加: オペレータ向けに現在のUWB距離を表示
//         if (current_m >= 0) {
//             printf(" 📡 [UWB Monitor] 現在のロボット距離: %.2f m (NLos: %d)\n", current_m, nlos);
//         } else {
//             printf(" 📡 [UWB Monitor] UWBデータ取得待機中...\n");
//         }

//         printf(" Guidance: (1)L<=%.1f, (2)<=%.1f, (3)<=%.1f, (4)<=%.1f, (5)<=%.1f\n", t1, t2, t3, t4, t5);
//         std::cout << "Enter target L [m]: ";

//         std::string input;
//         std::getline(std::cin, input);
//         if (input == "exit") return;

//         // 空エンターが押された場合は、画面（UWB距離）を更新して再入力待ちにする
//         if (input.empty()) continue;

//         try {
//             double L = std::stod(input);
//             int k = std::ceil(L / R);
//             k = std::clamp(k, 1, robot_num);

//             // 1. 各ノードの前端位置 P の計算
//             std::vector<double> P(node_num, 0.0);
//             P[3] = L; // CamN (Index 3)
//             if (k == 1) { P[2] = 2 * Lb; P[1] = 1 * Lb; } 
//             else if (k == 2) { P[2] = std::max(2 * Lb, L - R); P[1] = 1 * Lb; } 
//             else if (k == 3) { P[2] = std::max(2 * Lb, L - R); P[1] = std::max(1 * Lb, P[2] - R); }

//             // 2. 隙間 (Gap) の算出
//             std::vector<double> gaps(robot_num);
//             gaps[0] = P[3] - P[2] - Lb; // CamNの隙間
//             gaps[1] = P[2] - P[1] - Lb; // RN2の隙間
//             gaps[2] = P[1] - 0.0 - Lb;  // RN1の隙間

//             // 3. ★ルーティングの動的更新（ここが重要）
//             // CtlNの送信先(g_send_num)をkに設定
//             g_send_num.store(k);
            
//             // 下りパス（映像・ACKがCNへ戻る道）
//             routing_table[0][3] = (k == 1) ? "4" : "2"; // CamN -> CN(4) または RN2(2)
//             routing_table[1][3] = (k <= 2) ? "4" : "3"; // RN2 -> CN(4) または RN1(3)
//             routing_table[2][3] = "4";                  // RN1 -> CN(4)

//             // ★ ここを追加：上りパス（制御コマンドがCamNへ向かう道： routing_table[i][2] ）
//             routing_table[1][2] = (k >= 2) ? "1" : "0"; // RN2 -> CamN(1) （2-hop以上の時だけCamNへ）
//             routing_table[2][2] = (k == 3) ? "2" : "0"; // RN1 -> RN2(2)  （3-hopの時だけRN2へ）

//             // 4. コマンド文字列生成
//             std::string final_command;
//             for (int i = 0; i < robot_num; i++) {
//                 int cm = static_cast<int>(std::round(gaps[i] * 100));
//                 if (i == 0) {
//                     final_command += std::to_string(cm) + " " + routing_table[0][3] + ",";
//                 } else {
//                     final_command += std::to_string(cm) + " " + routing_table[i][2] + " " + routing_table[i][3] + ",";
//                     // final_command += std::to_string(cm) + " " + routing_table[i][3] + " " + routing_table[i][2] + ",";
//                 }
//             }
//             final_command.pop_back();

//             // 5. 送信
//             lock.lock();
//             if (!g_command_queue.empty()) g_command_queue.pop();
//             g_command_queue.push(final_command);
//             lock.unlock();

//             log.write_generate(std::chrono::duration<double>(hr_clock::now() - start_time), "Command", generate_num++, final_command.size(), final_command);
//             printf(">> Target: %.2fm (%d-hop), Command: %s\n", L, k, final_command.c_str());

//         } catch (...) { continue; }
//     }
// }

// // 一定間隔でダミーコマンドを生成し，キューに格納する関数
// void generate_command_fixed_interval(double generate_time_all, Log& log, hr_clock::time_point hr_start_time) {
//     double generate_command_interval = 0.1;  // 100ms ごとに コマンド生成
//     std::string command_data = "The control command is generated so that it is 60 bytes long";
//     std::chrono::duration<double> duration;
//     std::chrono::duration<double> log_time;

//     std::cout << "Start generate command data" << std::endl;
//     hr_clock::time_point generate_time_now;
//     hr_clock::time_point start_time = hr_start_time;

//     // int generate_num = 0;
//     while (true) {
//         generate_time_now = hr_clock::now();
//         duration = std::chrono::duration<double>(generate_time_now - start_time);
//         if (duration.count() >= generate_time_all) {
//             std::this_thread::sleep_for(std::chrono::milliseconds(100));  // コマンド生成後0.1秒待ったあと，終了
//             return;
//         }

//         g_lock.lock();
//         g_command_queue.push(command_data);
//         g_lock.unlock();

//         log_time = std::chrono::duration<double>(generate_time_now - start_time);

//         // ログに書き込む
//         // g_lock.lock();
//         log.write_generate(log_time, "Command", generate_num, command_data.size());
//         // g_lock.unlock();

//         generate_num++;
        
//         std::this_thread::sleep_for(std::chrono::milliseconds((int)(generate_command_interval*1000)));
//     }
// }

// // void ffmpeg_ts_mp4() {
// //     // ffmpegでtsファイルをmp4に変換
// //     std::string file_dir_pass = FILE_NAME_PREFIX + g_video_file_name + "/" + g_video_file_name;
// //     std::string ffmpeg_command = "ffmpeg -y -i " + file_dir_pass + ".ts" + " -c copy " + file_dir_pass + ".mp4 " + "-loglevel fatal";
// //     int system_command = std::system(ffmpeg_command.c_str());
// //     if (system_command == -1) {
// //         std::cerr << "Failed to execute ffmpeg command" << std::endl;
// //     } else {
// //         std::cout << "FFmpeg command executed successfully" << std::endl;
// //     }
// //     cout << "ffmpeg command: " << ffmpeg_command << endl;
// // }
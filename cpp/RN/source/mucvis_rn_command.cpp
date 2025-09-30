// 中継ノード c++ 版  同軸環境用
// 制御情報の処理
// パラメータを設定ファイルから読み込み

#include <iostream>
#include <thread>  // コンパイル時には-pthread
#include <queue>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <mutex>
#include <sstream>

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
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte
#define CONTROL_SEQ_MAX (1 << 30)  // 30bitの最大値
#define VIDEO_SEQ_MAX 0xffffffff  // 32bitの最大値
#define DUMMY_SEQ_MAX 3  // ダミーパケット送信回数上限

// グローバル変数
uint32_t g_control_seq = 0;  // 制御情報のシーケンス番号 0~2^30
uint32_t g_video_seq = 0;  // 映像シーケンス番号 0~2^32
uint32_t g_ack = 0;  // ack 0~2^30
const int g_video_queue_maxsize = 10;  // 映像データパケットキューの最大サイズ
std::queue<std::tuple<uint32_t, uint32_t, std::vector<uint8_t>>> g_video_queue;  // 映像データパケットキュー
std::queue<std::vector<uint8_t>> g_command_queue;  // 制御情報パケットキュー
std::queue<Packet> g_video_packet_queue;  // 映像データパケットキュー
std::queue<Packet> g_command_packet_queue;  // 制御情報パケットキュー
std::mutex g_lock;


class Mucvis_rn {
private:
    hr_clock::time_point hr_start_time;  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()
    int down_receiver_sock = socket(AF_INET, SOCK_DGRAM, 0);  // 下り受信用ソケット
    int up_receiver_sock = socket(AF_INET, SOCK_DGRAM, 0);  // 上り受信用ソケット
    struct sockaddr_in my_addr_down_receiver;
    struct sockaddr_in my_addr_up_receiver;
    struct sockaddr_in down_addr;
    struct sockaddr_in up_addr;
    Log *log;
    double ipt_interval;
    uint32_t m_ack = 0;  // ack 0~2^30
    const int m_video_queue_maxsize = 10;  // 映像データパケットキューの最大サイズ
    char down_buf[BUFFER_MAX];
    char up_buf[BUFFER_MAX];
    int my_node_num;
    std::vector<std::vector<std::string>> routing_table;
    std::string change_up_address;
    int send_node_before;  // 直前に送信したノード

    std::queue<Packet> m_video_packet_queue;  // 映像データパケットキュー
    std::queue<Packet> m_command_packet_queue;  // 制御情報パケットキュー  
    std::vector<uint8_t> send_payload;
    std::vector<uint8_t> down_recv_payload;
    std::vector<uint8_t> up_recv_payload;

public:
    Mucvis_rn(std::string my_address, int my_port_down_receiver, int my_port_up_receiver, std::string down_address, int down_port, std::string up_address, int up_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time, int my_node_num, std::vector<std::vector<std::string>>& routing_table) {
        // 受信用addr        
        my_addr_down_receiver.sin_family = AF_INET;
        my_addr_down_receiver.sin_addr.s_addr = inet_addr(my_address.c_str());
        my_addr_down_receiver.sin_port = htons(my_port_down_receiver);

        my_addr_up_receiver.sin_family = AF_INET;
        my_addr_up_receiver.sin_addr.s_addr = inet_addr(my_address.c_str());
        my_addr_up_receiver.sin_port = htons(my_port_up_receiver);

        // 送信用addr
        down_addr.sin_family = AF_INET;
        down_addr.sin_addr.s_addr = inet_addr(down_address.c_str());
        down_addr.sin_port = htons(down_port);

        up_addr.sin_family = AF_INET;
        up_addr.sin_addr.s_addr = inet_addr(up_address.c_str());
        up_addr.sin_port = htons(up_port);

        this->log = &log;
        this->ipt_interval = ipt_interval;
        this->hr_start_time = hr_start_time;
        this->my_node_num = my_node_num;
        this->routing_table = routing_table;
        this->change_up_address = routing_table[my_node_num - 1][1];  // 最初の送信先を設定
        this->send_node_before = std::stoi(routing_table[my_node_num - 1][2]);  // 最初の送信先ノードを設定

        send_payload.reserve(BUFFER_MAX);
        down_recv_payload.reserve(BUFFER_MAX);
        up_recv_payload.reserve(BUFFER_MAX);

        // 下り受信ソケットのバッファサイズを設定
        int recv_buffer_size = 1024 * 1024 * 10;  // 1MB
        if (setsockopt(down_receiver_sock, SOL_SOCKET, SO_RCVBUF, &recv_buffer_size, sizeof(recv_buffer_size)) == -1) {
            perror("setsockopt failed");
        }
    }


    // 下り受信用 ここから
    // パケット作成
    Packet make_packet_down_receiver() {
        uint32_t packet_type;
        g_lock.lock();
        int video_packet_queue_size = m_video_packet_queue.size();
        int command_packet_queue_size = m_command_packet_queue.size();
        g_lock.unlock();

        if (command_packet_queue_size != 0) {
            // 制御情報パケットがあるときは制御情報パケットを送信
            g_lock.lock();
            Packet packet = m_command_packet_queue.front();
            m_command_packet_queue.pop();
            g_lock.unlock();

            return packet;
        } else if(video_packet_queue_size != 0) {
            // 映像データパケットがあるときは映像データパケットを送信
            g_lock.lock();
            Packet packet = m_video_packet_queue.front();
            m_video_packet_queue.pop();
            g_lock.unlock();
            return packet;
        } else {  // 両方のパケットキューが空のとき，ダミーパケットを送信
            packet_type = TYPE_DUMMY;
            g_lock.lock();
            uint32_t ack = m_ack;
            g_lock.unlock();

            return Packet(packet_type, ack);
        }
    }

    // 下りパケット送信
    void down_receiver_send() {
        static std::mutex lock;
        uint32_t seq = 0;

        // パケット作成
        Packet packet = make_packet_down_receiver();
        // send_payload.clear();
        // send_payload = packet.get_payload();
        send_payload = std::move(packet.get_payload());  // ムーブで効率的に転送
        // std::vector<uint8_t> payload = packet.get_payload();

        std::string packet_type = packet.get_type();
        g_lock.lock();
        int video_packet_queue_size = m_video_packet_queue.size();
        g_lock.unlock();

        // パケットタイプがCONTROLのときは，上りに送信
        if (packet_type == "CONTROL") {
            // 上りへ送信
            sendto(down_receiver_sock, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&up_addr, sizeof(up_addr));
            
            hr_clock::time_point send_time = hr_clock::now();
            std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

            // ログに書き込む
            log->write_rn(duration, "Send", packet_type, "Up", seq, send_payload.size(), video_packet_queue_size);

            // 送信後，送信先をルーティングテーブルを参照し更新
            // ここ怪しい
            if (packet.get_command().find(',') != std::string::npos && up_addr.sin_addr.s_addr != inet_addr(change_up_address.c_str())) {
                up_addr.sin_addr.s_addr = inet_addr(change_up_address.c_str());  // 制御コマンド送信後に送信先を更新
                std::cout << "Change up address to: " << change_up_address << std::endl;

                if (change_up_address == "0") {
                    // キュー内をべて消す
                    lock.lock();
                    while (!m_command_packet_queue.empty()) {
                        m_command_packet_queue.pop();
                    }
                    while (!m_video_packet_queue.empty()) {
                        m_video_packet_queue.pop();
                    }
                    lock.unlock();
                    std::cout << "Clear queue and stop sending up." << std::endl;
                }
            }
        }

        // 下りへ送信
        sendto(down_receiver_sock, send_payload.data(), send_payload.size(), 0, (struct sockaddr *)&down_addr, sizeof(down_addr));
        
        hr_clock::time_point send_time = hr_clock::now();
        std::chrono::duration<double> duration = std::chrono::duration<double>(send_time - hr_start_time);

        // ログに書き込む
        if (packet_type == "VIDEO") {
            seq = packet.get_videoSeq();
        }

        log->write_rn(duration, "Send", packet_type, "Down", seq, send_payload.size(), video_packet_queue_size);
    }

    // 下りパケット受信
    void down_receiver_recv() {
        // char buf[BUFFER_MAX];
        // down_buf[0] = '\0';  // バッファを初期化
        uint32_t seq = 0;
        uint32_t ack = 0;
        g_lock.lock();
        int video_packet_queue_size = m_video_packet_queue.size();
        g_lock.unlock();

        int recv_size = recv(down_receiver_sock, down_buf, sizeof(down_buf), 0);

        hr_clock::time_point recv_time = hr_clock::now();
        // down_recv_payload.clear();
        // down_recv_payload = std::vector<uint8_t>(down_buf, down_buf + recv_size);
        down_recv_payload.assign(down_buf, down_buf + recv_size);  // ムーブで効率的に転送
        // std::vector<uint8_t> down_recv_payload(down_buf, down_buf + recv_size);
        Packet packet(down_recv_payload);
        std::string packet_type = packet.get_type();

        if (packet_type == "VIDEO") {
            ack = packet.get_ack();
            seq = packet.get_videoSeq();

            g_lock.lock();
            m_video_packet_queue.push(packet);
            g_lock.unlock();

            // キューがいっぱいのときは先頭の要素を削除
            if (video_packet_queue_size + 1 > m_video_queue_maxsize) {
                g_lock.lock();
                m_video_packet_queue.pop();
                g_lock.unlock();
                std::stringstream ss;
                ss << "T= " << std::chrono::duration<double>(recv_time - hr_start_time).count() 
                    << " Ev= Video_Packet_Drop"
                    << " Seq= " << seq;
                log->write(ss.str());
            }
        } else if (packet_type == "DUMMY") {
            ack = packet.get_ack();

            // 送信間隔 I / 3 待機
            // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));

        } else {  // CONTROL
            seq = packet.get_commandSeq();
            std::string command = packet.get_command();

            // 送信間隔 I / 3 待機
            // std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        }
        // ログ出力
        log->write_rn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, "Down", seq, recv_size, video_packet_queue_size);

        g_lock.lock();
        m_ack = ack;
        g_lock.unlock();

        // 送信間隔 I / 3 待機
        // if (packet_type == "DUMMY" or packet_type == "CONTROL") {
        std::this_thread::sleep_until(recv_time + std::chrono::duration<double>(ipt_interval / 3));
        // }
    }

    // 下りパケット受信開始
    int down_receiver_start() {
        // 下り受信用ソケットをバインド
        if (bind(down_receiver_sock, reinterpret_cast<sockaddr*>(&my_addr_down_receiver), sizeof(my_addr_down_receiver)) == -1) {
            std::cerr << "Failed to bind socket" << endl;
            close(down_receiver_sock);
            return 1;
        }
        cout << "Waiting down packet" << endl;

        while (true) {
            down_receiver_recv();
            down_receiver_send();
        }
    }
    // 下り受信用 ここまで


    // 上り受信用 ここから
    // 上りパケット受信
    void up_receiver_recv() {
        // char buf[BUFFER_MAX];
        // up_buf[0] = '\0';  // バッファを初期化
        uint32_t seq = 0;
        g_lock.lock();
        int video_packet_queue_size = m_video_packet_queue.size();
        g_lock.unlock();

        int recv_size = recv(up_receiver_sock, up_buf, sizeof(up_buf), 0);

        hr_clock::time_point recv_time = hr_clock::now();
        // std::vector<uint8_t> payload(up_buf, up_buf + recv_size);
        // up_recv_payload.clear();
        // up_recv_payload = std::vector<uint8_t>(up_buf, up_buf + recv_size);
        up_recv_payload.assign(up_buf, up_buf + recv_size);  // ムーブで効率的に転送
        Packet packet(up_recv_payload);
        std::string packet_type = packet.get_type();

        if (packet_type == "CONTROL") {
            seq = packet.get_commandSeq();
            g_lock.lock();
            if (change_up_address != "0") {
                m_command_packet_queue.push(packet);
            }
            // m_command_packet_queue.push(packet);
            g_lock.unlock();
            std::string command = packet.get_command();
            if (command.size() < 60) {
                cout << endl << "Recv command: " << command << endl;
            }
            // command内にコンマがあるか確認
            if (command.find(',') != std::string::npos) {
                // 制御コマンドがルーティングのとき，ルーティングテーブルを参照し送信先を更新
                try {
                    // 自分のノード番号より，コマンドからコンマまでを削除
                    for (int i = 0; i < my_node_num - 1; i++) {
                        command = command.substr(command.find(',') + 1);
                        // cout << "command after cut: " << command << endl;
                    }
                    std::string position = command.substr(0, command.find(' '));
                    command = command.substr(command.find(' ') + 1);
                    std::string send_up_node = command.substr(0, command.find(' '));
                    std::string send_down_node;
                    if (command.find(',') == std::string::npos) {
                        // 後ろにコンマがないときは，すべて取り出す
                        send_down_node = command.substr(command.find(' ') + 1);
                    } else {
                        send_down_node = command.substr(command.find(' ') + 1, command.find(',') - command.find(' ') - 1);
                    }

                    std::cout << "position: " << position << std::endl;
                    std::cout << "send_up_node: " << send_up_node << std::endl;
                    std::cout << "send_down_node: " << send_down_node << std::endl;

                    // 端末間距離をファイル出力
                    // 受信したposition（距離情報）をファイルに書き出す 河村追加0930------------------
                    std::ofstream pos_file("/tmp/robot_target_position.txt");
                    if (pos_file.is_open()) {
                        pos_file << position;
                        pos_file.close();
                    }
                    // -------------------- 提案コード20250930 --------------------

                    if (send_up_node != "0") {
                        // change_up_address = routing_table[std::stoi(send_node)-1][1];  // down
                        // up_addr.sin_addr.s_addr = inet_addr(change_up_address.c_str());

                        change_up_address = routing_table[std::stoi(send_up_node) - 1][1];  // up
                        
                        // 中継に参加するとき，先に送信先を更新
                        if (std::stoi(send_up_node) != 0) {
                            up_addr.sin_addr.s_addr = inet_addr(change_up_address.c_str());  // 制御コマンド送信後に送信先を更新
                            std::cout << "up_address: " << change_up_address << std::endl;
                        }
                    } else {
                        // 送信先をなくす
                        change_up_address = "0";
                        // up_addr.sin_port = htons(0);
                    }
                    if (send_down_node != "0") {
                        // std::string down_address = routing_table[std::stoi(send_node)-1][1];  // down
                        // down_addr.sin_addr.s_addr = inet_addr(down_address.c_str());

                        std::string down_address = routing_table[std::stoi(send_down_node) - 1][1];  // down
                        down_addr.sin_addr.s_addr = inet_addr(down_address.c_str());
                        std::cout << "down_address: " << down_address << std::endl;
                        cout << "Want to response to CN." << endl;
                    }
                }
                catch (...) {
                    // 例外が発生した場合の処理
                    // std::cerr << "Error parsing command or updating routing table." << std::endl;
                }
            }
        } else {
            cout << "Receive unknown packet type" << endl;
        }
        // ログ出力
        log->write_rn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, "Up", seq, recv_size, video_packet_queue_size);
        if (packet_type == "CONTROL") {
            log->write_command(std::chrono::duration<double>(recv_time - hr_start_time), "Command", seq, packet.get_command());
        } 
    }

    // 上りパケット受信開始
    int up_receiver_start() {
        if (bind(up_receiver_sock, reinterpret_cast<sockaddr*>(&my_addr_up_receiver), sizeof(my_addr_up_receiver)) == -1) {
            std::cerr << "Failed to bind socket" << endl;
            close(up_receiver_sock);
            return 1;
        }
        cout << "Waiting up packet" << endl;

        while (true) {
            up_receiver_recv();
        }
    }
    // 上り受信用 ここまで

    ~Mucvis_rn() {
        close(down_receiver_sock);
        close(up_receiver_sock);
    }
};


int main(int argc, char* argv[]) {
    system_clock::time_point system_start_time = system_clock::now();  // システム起動時刻 ノード間時刻同期用
    hr_clock::time_point hr_start_time = hr_clock::now();  // プログラム開始時刻 同一ノード内のログ出力用 std::chrono::high_resolution_clock::now()

    // 引数でパラメータ指定
    // 引数チェック ローカル用
    // if (argc != 6) {
    //     std::cerr << "Usage: " << argv[0] << " [My IP Address] [Up IP Address] [Down IP Address] [IPT interval(s)] [log_name]" << std::endl;
    //     return 1;
    // }

    // std::string host = argv[1];  // 自身のIPアドレス
    // std::string up_address = argv[2];  // 上り方向宛先IPアドレス
    // std::string down_address = argv[3];  // 下り方向宛先IPアドレス

    // // std::string my_IP = argv[1];
    // // std::string up_IP = argv[2];
    // // std::string down_IP = argv[3];
    // int up_port = 60201;  // ポート番号60202: 下り用
    // int down_port = 60202;  // ポート番号60201: 上り用
    // double ipt_interval = std::stod(argv[4]);  // 送信間隔 1msぐらい?

    // 設定ファイルからパラメータ読み込み
    // 引数チェック
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " [node_num] [log_name]" << endl;
        return 1;
    }
    // ファイルオープン
    std::ifstream ifs("../include/mucvis.conf");
    if (!ifs) {
        std::cerr << "Failed to open setting file: mucvis_setting.txt" << std::endl;
        return 1;
    }
    // パラメータ読み込み
    std::string parameter_list[] = {
        "node_num", "communication_range(m)", "Vehicle_body_length(m)", "IPT_interval(s)", "video_bit_rete(Mbps)", "time(s)","up_port", "down_port"
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

    // lineにnode_typeがあるまで読み飛ばす
    while(std::getline(ifs, line)) {
        if (line.find("node_type") != std::string::npos) {
            break;
        }
    }
    // 初期ルーティングテーブル読み込み
    std::vector<std::vector<std::string>> routing_table;
    while(std::getline(ifs, line)) {
        if (line.empty()) {
            break;
        }
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
    const double communication_range = std::stod(parameter_list[1]);  // 通信可能距離[m]
    const double Vehicle_body_length = std::stod(parameter_list[2]);  // 車両長[m]
    const double ipt_interval = std::stod(parameter_list[3]);  // 送信間隔 1msぐらい?
    const double video_bit_rate = std::stod(parameter_list[4]);  // 映像ビットレート [Mbps]
    const double generate_time_all = std::stod(parameter_list[5]);  // コマンド生成時間 [s]
    const int up_port = std::stoi(parameter_list[6]);  // ポート番号
    const int down_port = std::stoi(parameter_list[7]);  // ポート番号
    const int my_node_num = std::stoi(argv[1]);
    std::string host = routing_table[my_node_num - 1][1];  // 自身のIPアドレス
    int up_node = std::stoi(routing_table[my_node_num - 1][2]);
    int down_node = std::stoi(routing_table[my_node_num - 1][3]);
    std::string down_address = routing_table[down_node - 1][1];  // 宛先IPアドレス
    std::string up_address = routing_table[up_node - 1][1];  // 宛先IPアドレス
    // int send_socket = socket(AF_INET, SOCK_DGRAM, 0);

    // 上のパラメータを表示
    std::cout << "RN" << std::endl;
    std::cout << "node_num = " + std::to_string(node_num) << std::endl;
    std::cout << "communication_range = " + std::to_string(communication_range) + " m" << std::endl;
    std::cout << "Vehicle_body_length = " + std::to_string(Vehicle_body_length) + " m" << std::endl;
    std::cout << "IPT_interval = " + std::to_string(ipt_interval) + " s" << std::endl;
    std::cout << "video_bit_rete = " + std::to_string(video_bit_rate) + " Mbps" << std::endl;
    std::cout << "time = " + std::to_string(generate_time_all) + " s" << std::endl;
    std::cout << "up_port = " + std::to_string(up_port) << std::endl;
    std::cout << "down_port = " + std::to_string(down_port) << std::endl;
    std::cout << "my_node_num = " + std::to_string(my_node_num) << std::endl;
    std::cout << "my_IP_address = " + host << std::endl;
    std::cout << "up_node = " + std::to_string(up_node) << std::endl;
    std::cout << "up_address = " + up_address + ":" + std::to_string(up_port) << std::endl;
    std::cout << "down_node = " + std::to_string(down_node) << std::endl;
    std::cout << "down_address = " + down_address + ":" + std::to_string(down_port) << std::endl;
    std::cout << "routing_table:" << std::endl;
    for (const auto& row : routing_table) {
        for (const auto& item : row) {
            std::cout << item << " ";
        }
        std::cout << std::endl;
    }


    // ログファイルの作成
    // Log log("IPT", argv[5], system_start_time);
    Log log("IPT", argv[2], system_start_time);
    log.write("RN");
    log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");

    // --- 河村追加0930 ここからモーター制御プログラムをバックグラウンドで起動する処理 ---
    pid_t motor_pid = fork();
    if (motor_pid == -1) {
        // forkに失敗した場合
        perror("fork failed to start motor control program");
    } else if (motor_pid == 0) {
        // 子プロセス: モーター制御プログラムを実行する
        std::cout << "Starting motor control program in the background..." << std::endl;
        
        // モーター制御プログラムの実行ファイルへの絶対パス
        const char* motor_program_path = "/home/pi/robot_project/Motor_Driver_HAT_Code/Motor_Driver_HAT_Code/Raspberry Pi/c";
        
        // execlでプログラムを起動
        // この通信プログラム自体をsudoで実行する必要があります
        execl(motor_program_path, motor_program_path, (char *)NULL);
        
        // execlが失敗した場合のみ、以下のコードが実行される
        perror("execl failed to run motor program");
        exit(1); // 子プロセスを終了
    }
    // --- ここまで ---

    // cout << "RN" << std::endl;
    // cout << "My_IP_address = " << host << std::endl;
    // cout << "up_address = " << up_address << std::endl;
    // cout << "down_address = " << down_address << std::endl;


    // 実験環境用
    Mucvis_rn mucvis_rn(host, down_port, up_port, down_address, down_port, up_address, up_port, log, ipt_interval, hr_start_time, my_node_num, routing_table);

    // ローカル環境用(ポートで振り分け)
    // Mucvis_rn mucvis_rn(host, 60202, 60203, down_address, 60204, up_address, 60201, log, ipt_interval, hr_start_time);

    // スレッド開始
    std::thread recv_down_receiver_thread(&Mucvis_rn::down_receiver_start, &mucvis_rn);
    std::this_thread::sleep_for(std::chrono::milliseconds(1));  // 1ms待機
    std::thread recv_up_receiver_thread(&Mucvis_rn::up_receiver_start, &mucvis_rn);
    recv_down_receiver_thread.join();
    recv_up_receiver_thread.join();

    return 0;
}

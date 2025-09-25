// 中継ノード c++ 版  同軸環境用
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

    std::queue<Packet> m_video_packet_queue;  // 映像データパケットキュー
    std::queue<Packet> m_command_packet_queue;  // 制御情報パケットキュー  
    std::vector<uint8_t> send_payload;
    std::vector<uint8_t> down_recv_payload;
    std::vector<uint8_t> up_recv_payload;

public:
    Mucvis_rn(std::string my_address, int my_port_down_receiver, int my_port_up_receiver, std::string down_address, int down_port, std::string up_address, int up_port, Log& log, double ipt_interval, hr_clock::time_point hr_start_time) {
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
            m_command_packet_queue.push(packet);
            g_lock.unlock();
        } else {
            cout << "Receive unknown packet type" << endl;
        }
        // ログ出力
        log->write_rn(std::chrono::duration<double>(recv_time - hr_start_time), "Recv", packet_type, "Up", seq, recv_size, video_packet_queue_size);
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

    // 引数チェック ローカル用
    if (argc != 6) {
        std::cerr << "Usage: " << argv[0] << " [My IP Address] [Up IP Address] [Down IP Address] [IPT interval(s)] [log_name]" << std::endl;
        return 1;
    }

    std::string host = argv[1];  // 自身のIPアドレス
    std::string up_address = argv[2];  // 上り方向宛先IPアドレス
    std::string down_address = argv[3];  // 下り方向宛先IPアドレス

    // std::string my_IP = argv[1];
    // std::string up_IP = argv[2];
    // std::string down_IP = argv[3];
    int up_port = 60201;  // ポート番号60202: 下り用
    int down_port = 60202;  // ポート番号60201: 上り用
    double ipt_interval = std::stod(argv[4]);  // 送信間隔 1msぐらい?

    // ログファイルの作成
    Log log("IPT", argv[5], system_start_time);
    log.write("RN");
    log.write("ipt_interval = " + std::to_string(ipt_interval) + " s");

    cout << "RN" << std::endl;
    cout << "My_IP_address = " << host << std::endl;
    cout << "up_address = " << up_address << std::endl;
    cout << "down_address = " << down_address << std::endl;


    // 実験環境用
    Mucvis_rn mucvis_rn(host, down_port, up_port, down_address, down_port, up_address, up_port, log, ipt_interval, hr_start_time);

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

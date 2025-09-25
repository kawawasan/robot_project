// MUCViSのパケットクラスの宣言

#ifndef PACKET_HPP
#define PACKET_HPP

#include <string>
#include <cstring>

// パケットタイプ 映像: 0, 制御情報: 1, ダミー: 2 31と30bit目
#define TYPE_VIDEO 0  // (00 << 30)
#define TYPE_CONTROL (0b01 << 30)
#define TYPE_DUMMY (0b10 << 30)
#define NAX_PAYLOAD_SIZE 1472  // ペイロードサイズ 最大1472byte
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte
#define MAX_COMMAND_SIZE 60  // 制御情報サイズ 最大60byte

class Packet {
    private:
        uint32_t top4bytes;  // ペイロードの先頭4バイト
        uint32_t type;  // パケットタイプ 2bit
        uint32_t ack;  // ack 30bit
        uint32_t seq;  // シーケンス番号 video:32bit control:30bit
        uint8_t videoData[MAX_VIDEO_SIZE];  // 映像データ
        std::string command;  // 制御情報
        uint8_t payload[NAX_PAYLOAD_SIZE];   // ペイロード

    public:
        // パケット受信時のコンストラクタ
        Packet(uint8_t *payload);

        // ビデオパケット生成時のコンストラクタ
        Packet(uint32_t type, uint32_t ack, uint32_t seq, uint8_t* videoData);

        // コマンドパケット生成時のコンストラクタ
        Packet(uint32_t type, uint32_t seq, std::string command);

        // ダミーパケット生成時のコンストラクタ
        Packet(uint32_t type, uint32_t ack);

        std::string get_type();
        uint8_t* get_payload();
        int get_ack();
        int get_videoSeq();
        int get_commandSeq();
        uint8_t* get_videoData();
        std::string get_command();
};

#endif // PACKET_HPP

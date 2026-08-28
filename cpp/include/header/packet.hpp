// MUCViSのパケットクラスの宣言

#ifndef PACKET_HPP
#define PACKET_HPP

#include <string>
#include <cstring>
#include <vector>
#include <array>
#include <cstdint>

class Packet {
    private:
        uint32_t top4bytes;  // ペイロードの先頭4バイト
        uint32_t type;  // パケットタイプ 2bit
        uint32_t ack;  // ack 30bit
        uint32_t seq;  // シーケンス番号 video:32bit control:30bit
        // uint8_t videoData[MAX_VIDEO_SIZE];  // 映像データ
        std::vector<uint8_t> videoData;  // 映像データ
        std::string command;  // 制御情報
        // uint8_t payload[NAX_PAYLOAD_SIZE];   // ペイロード
        std::vector<uint8_t> payload;  // ペイロード

    public:
        static constexpr int DIST_SLOT_COUNT = 3;              // RN1, RN2, CamN
        static constexpr int16_t DIST_NO_DATA = INT16_MIN;      // このサイクルで更新なし
        static constexpr int DIST_BYTES = DIST_SLOT_COUNT * sizeof(int16_t);  // 6
        // パケット受信時のコンストラクタ
        Packet(std::vector<uint8_t> payload);
        // Packet(uint8_t *payload);

        // ビデオパケット生成時のコンストラクタ
        Packet(uint32_t type, uint32_t ack, uint32_t seq, std::vector<uint8_t> videoData);
        // Packet(uint32_t type, uint32_t ack, uint32_t seq, uint8_t* videoData);

        // コマンドパケット生成時のコンストラクタ
        Packet(uint32_t type, uint32_t seq, std::string command);

        // ダミーパケット生成時のコンストラクタ
        Packet(uint32_t type, uint32_t ack, uint32_t seq);

        std::string get_type();
        std::vector<uint8_t> get_payload();
        // uint8_t* get_payload();
        int get_ack();
        int get_videoSeq();
        int get_commandSeq();
        int get_dummySeq();
        std::vector<uint8_t> get_videoData();
        // uint8_t* get_videoData();
        std::string get_command();
        std::array<int16_t, DIST_SLOT_COUNT> get_distances();
        void set_distance(int node_idx, int16_t distance_cm);
};

#endif // PACKET_HPP

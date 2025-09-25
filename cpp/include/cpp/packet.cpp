// MUCViSのパケットクラスの実装

#include "../header/packet.hpp"
#include <iostream>

// パケットタイプ 映像: 0, 制御情報: 1, ダミー: 2 31と30bit目
#define TYPE_VIDEO (uint32_t)0  // (00 << 30)
#define TYPE_CONTROL (uint32_t)(0b01 << 30)
#define TYPE_DUMMY (uint32_t)(0b10 << 30)
#define NAX_PAYLOAD_SIZE 1472  // ペイロードサイズ 最大1472byte
#define MAX_VIDEO_SIZE 1464  // 映像データサイズ 最大1464byte
#define MAX_COMMAND_SIZE 60  // 制御情報サイズ 最大60byte


// パケット受信時のコンストラクタ
Packet::Packet(std::vector<uint8_t> payload) {
    this->payload.reserve(NAX_PAYLOAD_SIZE);
    // ペイロードをコピー
    this->payload = payload;
    // ペイロードから4バイト取り出してtop4bytesに格納
    memcpy(&top4bytes, this->payload.data(), sizeof(top4bytes));
    type = top4bytes >> 30 << 30;  // 先頭2bitを取り出してtypeに格納
}

// ビデオパケット生成時のコンストラクタ
Packet::Packet(uint32_t type, uint32_t ack, uint32_t seq, std::vector<uint8_t> videoData) {
    this->videoData.reserve(MAX_VIDEO_SIZE);
    payload.clear();
    payload.reserve(NAX_PAYLOAD_SIZE);
    this->type = type;
    this->ack = ack;
    top4bytes = this->type + this->ack;
    this->seq = seq;
    // 繋げてペイロードに変形
    uint32_t header[2] = {this->type + this->ack, this->seq};
    payload.insert(payload.end(), reinterpret_cast<uint8_t*>(header), reinterpret_cast<uint8_t*>(header) + sizeof(header));
    payload.insert(payload.end(), videoData.begin(), videoData.end());

    // uint32_t header[2] = {top4bytes, this->seq};
    
    // memcpy(payload, header, 8);
    // memcpy(payload + 8, videoData, MAX_VIDEO_SIZE);
}

// コマンドパケット生成時のコンストラクタ
Packet::Packet(uint32_t type, uint32_t seq, std::string command) {
    payload.clear();
    payload.reserve(NAX_PAYLOAD_SIZE);
    this->type = type;
    this->seq = seq;
    // 繋げてペイロードに変形
    top4bytes = this->type + this->seq;
    payload.insert(payload.end(), reinterpret_cast<uint8_t*>(&top4bytes), reinterpret_cast<uint8_t*>(&top4bytes) + sizeof(top4bytes));
    payload.insert(payload.end(), command.begin(), command.end());

    // memcpy(payload, &top4bytes, 4);
    // memcpy(payload + 4, command.c_str(), command.size());
}

// ダミーパケット生成時のコンストラクタ
Packet::Packet(uint32_t type, uint32_t ack) {
    payload.clear();
    payload.reserve(NAX_PAYLOAD_SIZE);
    this->type = type;
    this->ack = ack;
    // 繋げてペイロードに変形
    top4bytes = this->type + this->ack;
    payload.insert(payload.end(), reinterpret_cast<uint8_t*>(&top4bytes), reinterpret_cast<uint8_t*>(&top4bytes) + sizeof(top4bytes));

    // memcpy(payload, &top4bytes, 4);
}

std::string Packet::get_type() {
    if (type == TYPE_VIDEO) {
        return "VIDEO";
    } else if (type == TYPE_CONTROL) {
        return "CONTROL";
    } else if (type == (uint32_t)TYPE_DUMMY) {
        return "DUMMY";
    } else {
        return "UNKNOWN";
    }
}

std::vector<uint8_t> Packet::get_payload() {
    return payload;
}

int Packet::get_ack() {
    ack = top4bytes - type;
    return ack;
}

int Packet::get_videoSeq() {
    memcpy(&seq, payload.data() + 4, sizeof(seq));
    // seq = *reinterpret_cast<uint32_t*>(payload + 4);
    return seq;
}

int Packet::get_commandSeq() {
    seq = top4bytes - type;
    return seq;
}

std::vector<uint8_t> Packet::get_videoData() {
    videoData.clear();
    videoData.insert(videoData.end(), payload.begin() + 8, payload.end());
    // memcpy(videoData, payload + 8, MAX_VIDEO_SIZE);
    return videoData;
}

std::string Packet::get_command() {
    command = std::string(payload.begin() + 4, payload.end());
    // command = std::string(payload + 4, payload + 4 + MAX_COMMAND_SIZE);
    return command;
}

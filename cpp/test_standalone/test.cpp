//テスト用，河村20260827

#include "../header/packet.hpp"
#include <cassert>
#include <iostream>



int main() {
       // DUMMYパケット：8byte → 14byteになっているか
    Packet dummy(2u << 30 /*TYPE_DUMMY*/, 5, 42);
    auto dummy_payload = dummy.get_payload();
    assert(dummy_payload.size() == 14);  // 8(既存ヘッダ) + 6(距離)
    Packet dummy2(dummy_payload);
    assert(dummy2.get_dummySeq() == 42);
    auto dd = dummy2.get_distances();
    assert(dd[0] == Packet::DIST_NO_DATA);  // 初期値のまま

    // CONTROLパケット：サイズが変わっていないか（無変更の確認）
    Packet ctrl(1u << 30 /*TYPE_CONTROL*/, 7, std::string("test_command"));
    auto ctrl_payload = ctrl.get_payload();
    assert(ctrl_payload.size() == 4 + std::string("test_command").size());  // 距離分の6byteが含まれていないこと

    std::cout << "OK: DUMMY/CONTROL packet tests passed" << std::endl;
    std::vector<uint8_t> video_bytes = {1, 2, 3, 4, 5};
    Packet p(0 /*TYPE_VIDEO*/, 5, 10, video_bytes);
    p.set_distance(0, 123);
    p.set_distance(1, 456);
    p.set_distance(2, 789);

    auto payload = p.get_payload();
    Packet p2(payload);  // 受信時コンストラクタで再構築
    auto d = p2.get_distances();

    assert(d[0] == 123 && d[1] == 456 && d[2] == 789);
    assert(p2.get_videoData() == video_bytes);

    std::cout << "OK: VIDEO packet round-trip test passed" << std::endl;
    return 0;

}
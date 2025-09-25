// バイト列を扱うキュークラスの宣言

#ifndef BYTEQUEUE_HPP
#define BYTEQUEUE_HPP

#include <vector>
#include <cstdint>
#include <mutex>

class ByteQueue {
private:
    std::vector<uint8_t> queue;

public:
    // データをキューに追加
    void put(const std::vector<uint8_t>& data);

    // キューから指定サイズのデータを取り出す
    std::vector<uint8_t> get(size_t size);

    // キューのサイズを返す
    size_t size() const;
};

#endif // BYTEQUEUE_HPP

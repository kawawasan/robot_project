// バイト列を扱うキュークラスの実装

#include "../header/bytequeue.hpp"

void ByteQueue::put(const std::vector<uint8_t>& data) {
    queue.insert(queue.end(), data.begin(), data.end());
}

std::vector<uint8_t> ByteQueue::get(size_t size) {
    if (size > queue.size()) {
        size = queue.size();
    }
    std::vector<uint8_t> data(queue.begin(), queue.begin() + size);
    queue.erase(queue.begin(), queue.begin() + size);
    return data;
}

size_t ByteQueue::size() const {
    return queue.size();
}

// MUCViS統合用にC++に書き換えた測距プログラム

#include <iostream>
#include <string>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <stdio.h>
#include <chrono>
#include <thread>

// I2Cバス番号とデバイスアドレス
const std::string I2C_BUS_PATH = "/dev/i2c-1"; // Raspberry Pi 3/4のデフォルトI2Cバス1
const int LIDAR_ADDRESS = 0x62;              // Lidar Lite v3 のI2Cアドレス

// レジスタアドレスの定義
const int ACQ_COMMAND = 0x00;
const int STATUS = 0x01;
const int FULL_DELAY_HIGH = 0x0f;
const int FULL_DELAY_LOW = 0x10;

/**
 * Lidar Lite v3 からの距離を読み取る関数
 * @param i2c_fd I2Cデバイスファイルディスクリプタ
 * @return 測定距離 (cm)。エラー時は負の値を返す。
 */
int read_distance(int i2c_fd) {
    // 1. 測定開始コマンド (0x00 に 0x04 を書き込む)
    // Python: bus.write_block_data(address, ACQ_COMMAND, [0x04])
    unsigned char write_buffer[2] = {ACQ_COMMAND, 0x04};
    if (write(i2c_fd, write_buffer, 2) != 2) {
        std::cerr << "Error: Failed to write command to LIDAR." << std::endl;
        return -1;
    }

    // 2. 0x01 (STATUS) を読み込んで、最下位ビットが0になるまで待つ
    // Python: while value & 0x01 == 1: ...
    unsigned char status_reg = STATUS;
    unsigned char status_value;
    int attempts = 0;
    const int max_attempts = 100; // タイムアウトを設定

    do {
        // 0x01レジスタアドレスを送信
        if (write(i2c_fd, &status_reg, 1) != 1) {
            std::cerr << "Error: Failed to set status register address." << std::endl;
            return -2;
        }

        // 1バイト読み取り
        if (read(i2c_fd, &status_value, 1) != 1) {
            std::cerr << "Error: Failed to read status register." << std::endl;
            return -3;
        }

        if (attempts++ >= max_attempts) {
            std::cerr << "Error: LIDAR busy timeout." << std::endl;
            return -4;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1)); // 1ms待機
    } while (status_value & 0x01); // 最下位ビットが1 (busy) の間ループ

    // 3. 0x0f (FULL_DELAY_HIGH) から2バイト読み込んで距離を取得する
    // Python: high/low = bus.read_byte_data(...)
    unsigned char distance_reg = FULL_DELAY_HIGH;
    unsigned char distance_buffer[2];
    
    // 0x0f レジスタアドレスを送信
    if (write(i2c_fd, &distance_reg, 1) != 1) {
        std::cerr << "Error: Failed to set distance register address." << std::endl;
        return -5;
    }
    
    // 2バイト読み取り (0x0f (High), 0x10 (Low))
    if (read(i2c_fd, distance_buffer, 2) != 2) {
        std::cerr << "Error: Failed to read distance data." << std::endl;
        return -6;
    }

    // 16bitの測定距離をcm単位で取得
    int dist = (distance_buffer[0] << 8) | distance_buffer[1];
    return dist;
}

int main() {
    // 1. I2Cバスを開く
    int i2c_fd = open(I2C_BUS_PATH.c_str(), O_RDWR);
    if (i2c_fd < 0) {
        perror("Error: Failed to open the I2C bus");
        std::cerr << "Check if I2C is enabled (sudo raspi-config) and permissions." << std::endl;
        return 1;
    }

    // 2. I2Cアドレスを設定
    if (ioctl(i2c_fd, I2C_SLAVE, LIDAR_ADDRESS) < 0) {
        perror("Error: Failed to acquire bus access and/or talk to slave");
        close(i2c_fd);
        return 1;
    }

    std::cout << "Lidar Lite v3 I2C Test Started." << std::endl;

    while (true) {
        int dist_cm = read_distance(i2c_fd);

        if (dist_cm >= 0) {
            double dist_m = (double)dist_cm / 100.0;
            printf("Dist = %d cm , %.2f m\n", dist_cm, dist_m);
        } else {
            std::cerr << "Measurement failed with error code: " << dist_cm << std::endl;
        }

        // 1秒待機 (time.sleep(1) に相当)
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    close(i2c_fd); // 実際には無限ループのため到達しない
    return 0;
}
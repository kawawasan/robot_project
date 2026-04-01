#include "main.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <time.h>
#include <math.h> // fabsなどを使う場合に備えて一応含めますが、今回は比較演算子で対応

// --- LIDAR関連の定義 ---
const char* I2C_BUS_PATH = "/dev/i2c-1";
const int LIDAR_ADDRESS = 0x62;
const int ACQ_COMMAND = 0x00;
const int STATUS = 0x01;
const int FULL_DELAY_HIGH = 0x0f;

// --- 目標距離ファイル ---
const char* TARGET_POSITION_FILE = "/tmp/robot_target_position.txt";
const int MOVE_SPEED = 80; // 移動速度

int i2c_fd = -1; // I2Cファイルディスクリプタ

/**
 * @brief LIDARの初期化
 */
int init_lidar() {
    i2c_fd = open(I2C_BUS_PATH, O_RDWR);
    if (i2c_fd < 0) {
        perror("Error: Failed to open the I2C bus");
        return -1;
    }
    if (ioctl(i2c_fd, I2C_SLAVE, LIDAR_ADDRESS) < 0) {
        perror("Error: Failed to acquire bus access to slave");
        close(i2c_fd);
        return -1;
    }
    printf("Lidar Lite v3 Initialized.\n");
    return 0;
}

/**
 * @brief LIDARから距離(cm)を読み取る
 */
int get_lidar_distance_cm() {
    if (i2c_fd < 0) return -1;

    // 測定開始コマンド
    unsigned char write_buffer[2] = {ACQ_COMMAND, 0x04};
    if (write(i2c_fd, write_buffer, 2) != 2) {
        fprintf(stderr, "Error: Failed to write command to LIDAR.\n");
        return -1;
    }

    // ステータス待機
    unsigned char status_reg = STATUS;
    unsigned char status_value;
    int attempts = 0;
    do {
        if (write(i2c_fd, &status_reg, 1) != 1) return -2;
        if (read(i2c_fd, &status_value, 1) != 1) return -3;
        if (attempts++ > 100) {
            fprintf(stderr, "Error: LIDAR busy timeout.\n");
            return -4;
        }
        usleep(1000); 
    } while (status_value & 0x01);

    // 距離データ読み込み
    unsigned char distance_reg = FULL_DELAY_HIGH;
    unsigned char distance_buffer[2];
    if (write(i2c_fd, &distance_reg, 1) != 1) return -5;
    if (read(i2c_fd, distance_buffer, 2) != 2) return -6;

    return (distance_buffer[0] << 8) | distance_buffer[1];
}

/**
 * @brief ファイルから目標距離(m)を読み取る
 */
double read_target_position_m() {
    FILE *fp = fopen(TARGET_POSITION_FILE, "r");
    if (fp == NULL) {
        return -1.0; 
    }

    double position_cm;
    if (fscanf(fp, "%lf", &position_cm) != 1) {
        fclose(fp);
        return -2.0; 
    }

    fclose(fp);
    return position_cm / 100.0; // cm -> m
}

void Handler(int signo)
{
    printf("\r\nHandler:Motor Stop\r\n");
    Motor_Stop(MOTORA);
    Motor_Stop(MOTORB);
    if (i2c_fd >= 0) {
        close(i2c_fd);
    }
    DEV_ModuleExit();
    exit(0);
}

int main(void)
{
    // モジュールとモーターの初期化
    if(DEV_ModuleInit()) exit(1);
    Motor_Init();

    // LIDARの初期化
    if (init_lidar() != 0) {
        DEV_ModuleExit();
        exit(1);
    }

    signal(SIGINT, Handler);
    printf("Starting low-frequency LIDAR control loop (1Hz)...\n");

    // 時間管理用の変数
    struct timespec last_measure_time;
    clock_gettime(CLOCK_MONOTONIC, &last_measure_time);
    
    int dist_cm = 0; // 最新の測定値を保持
    const double STOP_TOLERANCE = 0.05; // 5cmの許容誤差

    while(1) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);

        // 前回の測定から何秒経過したか計算
        double elapsed = (now.tv_sec - last_measure_time.tv_sec) + 
                         (now.tv_nsec - last_measure_time.tv_nsec) / 1e9;

        // --- 1.0秒ごとにLIDARの測定を実行 ---
        if (elapsed >= 1.0) {
            int new_dist = get_lidar_distance_cm();
            if (new_dist >= 0) {
                dist_cm = new_dist;
                last_measure_time = now; // 測定成功時のみタイマーリセット
                printf("[LIDAR] Updated Distance: %d cm\n", dist_cm);
            } else {
                // 測定失敗時は安全のためモーター停止
                fprintf(stderr, "LIDAR read error! Stopping motors for safety.\n");
                Motor_Stop(MOTORA);
                Motor_Stop(MOTORB);
                usleep(500 * 1000);
                continue; 
            }
        }

        // --- 目標距離の読み取りと制御ロジック ---
        double current_distance_m = (double)dist_cm / 100.0;
        double target_distance_m = read_target_position_m();

        if (target_distance_m >= 0 && dist_cm > 0) {
            // 目標より遠い (前進)
            if (current_distance_m > target_distance_m + STOP_TOLERANCE) {
                Motor_Run(MOTORA, BACKWARD, MOVE_SPEED);
                Motor_Run(MOTORB, BACKWARD, MOVE_SPEED);
            } 
            // 目標より近い (後退)
            else if (current_distance_m < target_distance_m - STOP_TOLERANCE) {
                Motor_Run(MOTORA, FORWARD, MOVE_SPEED);
                Motor_Run(MOTORB, FORWARD, MOVE_SPEED);
            } 
            // 範囲内 (停止)
            else {
                Motor_Stop(MOTORA);
                Motor_Stop(MOTORB);
            }
        } else {
            // 目標ファイルが読み込めない場合などは停止
            Motor_Stop(MOTORA);
            Motor_Stop(MOTORB);
        }

        // ループ自体の待機（0.1秒）。これにより目標ファイルの更新を素早くチェックできる
        usleep(100 * 1000); 
    }

    // ここには到達しませんが、念のため
    Handler(0);
    return 0;
}
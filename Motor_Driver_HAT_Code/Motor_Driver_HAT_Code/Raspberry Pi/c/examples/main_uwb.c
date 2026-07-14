// 新規main UWB考慮プログラム
#include "main.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <time.h>
#include <signal.h>
#include <string.h>

// --- 共通の定数・変数 ---
const char* TARGET_POSITION_FILE = "/tmp/robot_target_position.txt";
const char* UWB_CURRENT_FILE     = "/tmp/uwb_current_distance.txt";
const int MOVE_SPEED = 80;
const double STOP_TOLERANCE = 0.05;

// --- LiDAR専用の定数・変数 ---
const char* I2C_BUS_PATH = "/dev/i2c-1";
const int LIDAR_ADDRESS = 0x62;
const int ACQ_COMMAND = 0x00;
const int STATUS = 0x01;
const int FULL_DELAY_HIGH = 0x0f;
int i2c_fd = -1;

// --- 関数プロトタイプ ---
void run_lidar_mode();
void run_uwb_mode();
int get_lidar_distance_cm();
double read_target_position_m();
void Handler(int signo);

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("エラー: モードを指定してください (./main [lidar|uwb])\n");
        return -1;
    }

    if(DEV_ModuleInit()) exit(1);
    Motor_Init();
    signal(SIGINT, Handler);

    if (strcmp(argv[1], "lidar") == 0) {
        run_lidar_mode();
    } else if (strcmp(argv[1], "uwb") == 0) {
        run_uwb_mode();
    } else {
        printf("不明なモード: %s\n", argv[1]);
    }
    return 0;
}

// ---------------------------------------------------------
// ライダー制御ロジック (元の要素をフル搭載)
// ---------------------------------------------------------
void run_lidar_mode() {
    i2c_fd = open(I2C_BUS_PATH, O_RDWR);
    if (i2c_fd < 0) { perror("I2C open error"); exit(1); }
    if (ioctl(i2c_fd, I2C_SLAVE, LIDAR_ADDRESS) < 0) { perror("I2C slave error"); exit(1); }
    
    printf("--- LiDARモードで制御開始 ---\n");
    while(1) {
        int dist_cm = get_lidar_distance_cm();
        double target_m = read_target_position_m();
        
        if (target_m >= 0 && dist_cm > 0) {
            double current_m = (double)dist_cm / 100.0;
            if (current_m > target_m + STOP_TOLERANCE) {
                Motor_Run(MOTORA, BACKWARD, MOVE_SPEED);
                Motor_Run(MOTORB, BACKWARD, MOVE_SPEED);
            } else if (current_m < target_m - STOP_TOLERANCE) {
                Motor_Run(MOTORA, FORWARD, MOVE_SPEED);
                Motor_Run(MOTORB, FORWARD, MOVE_SPEED);
            } else {
                Motor_Stop(MOTORA); Motor_Stop(MOTORB);
            }
        }
        usleep(50000); // 50ms周期
    }
}

int get_lidar_distance_cm() {
    unsigned char write_buffer[2] = {ACQ_COMMAND, 0x04};
    if (write(i2c_fd, write_buffer, 2) != 2) return -1;

    unsigned char status_reg = STATUS, status_value;
    int attempts = 0;
    do {
        write(i2c_fd, &status_reg, 1);
        read(i2c_fd, &status_value, 1);
        if (attempts++ > 100) return -4;
        usleep(1000);
    } while (status_value & 0x01);

    unsigned char distance_reg = FULL_DELAY_HIGH, distance_buffer[2];
    write(i2c_fd, &distance_reg, 1);
    read(i2c_fd, distance_buffer, 2);
    return (distance_buffer[0] << 8) | distance_buffer[1];
}

// ---------------------------------------------------------
// UWB制御ロジック
// ---------------------------------------------------------
void run_uwb_mode() {
    printf("--- UWBモードで制御開始 ---\n");
    while(1) {
        double target_m = read_target_position_m();
        FILE *fp = fopen(UWB_CURRENT_FILE, "r");
        if (fp) {
            int nlos; double current_cm;
            if (fscanf(fp, "%d,%lf", &nlos, &current_cm) == 2) {
                double current_m = current_cm / 100.0;
                if (target_m >= 0) {
                    if (current_m > target_m + STOP_TOLERANCE) {
                        Motor_Run(MOTORA, BACKWARD, MOVE_SPEED);
                        Motor_Run(MOTORB, BACKWARD, MOVE_SPEED);
                    } else if (current_m < target_m - STOP_TOLERANCE) {
                        Motor_Run(MOTORA, FORWARD, MOVE_SPEED);
                        Motor_Run(MOTORB, FORWARD, MOVE_SPEED);
                    } else {
                        Motor_Stop(MOTORA); Motor_Stop(MOTORB);
                    }
                }
            }
            fclose(fp);
        }
        usleep(100000); // 100ms周期
    }
}

// ---------------------------------------------------------
// 共通補助関数
// ---------------------------------------------------------
double read_target_position_m() {
    FILE *fp = fopen(TARGET_POSITION_FILE, "r");
    double pos = -1.0;
    if (fp) { fscanf(fp, "%lf", &pos); fclose(fp); }
    return pos;
}

void Handler(int signo) {
    printf("\r\nHandler:Motor Stop\r\n");
    Motor_Stop(MOTORA);
    Motor_Stop(MOTORB);
    if (i2c_fd >= 0) close(i2c_fd);
    DEV_ModuleExit();
    exit(0);
}

// #include "main.h"
// #include <stdio.h>
// #include <stdlib.h>
// #include <unistd.h>
// #include <fcntl.h>
// #include <sys/ioctl.h>
// #include <linux/i2c-dev.h>
// #include <time.h>
// #include <math.h> // fabsなどを使う場合に備えて一応含めますが、今回は比較演算子で対応

// // --- LIDAR関連の定義 ---
// const char* I2C_BUS_PATH = "/dev/i2c-1";
// const int LIDAR_ADDRESS = 0x62;
// const int ACQ_COMMAND = 0x00;
// const int STATUS = 0x01;
// const int FULL_DELAY_HIGH = 0x0f;

// // --- 目標距離ファイル ---
// const char* TARGET_POSITION_FILE = "/tmp/robot_target_position.txt";
// const int MOVE_SPEED = 80; // 移動速度

// int i2c_fd = -1; // I2Cファイルディスクリプタ

// /**
//  * @brief LIDARの初期化
//  */
// int init_lidar() {
//     i2c_fd = open(I2C_BUS_PATH, O_RDWR);
//     if (i2c_fd < 0) {
//         perror("Error: Failed to open the I2C bus");
//         return -1;
//     }
//     if (ioctl(i2c_fd, I2C_SLAVE, LIDAR_ADDRESS) < 0) {
//         perror("Error: Failed to acquire bus access to slave");
//         close(i2c_fd);
//         return -1;
//     }
//     printf("Lidar Lite v3 Initialized.\n");
//     return 0;
// }

// /**
//  * @brief LIDARから距離(cm)を読み取る
//  */
// int get_lidar_distance_cm() {
//     if (i2c_fd < 0) return -1;

//     // 測定開始コマンド
//     unsigned char write_buffer[2] = {ACQ_COMMAND, 0x04};
//     if (write(i2c_fd, write_buffer, 2) != 2) {
//         fprintf(stderr, "Error: Failed to write command to LIDAR.\n");
//         return -1;
//     }

//     // ステータス待機
//     unsigned char status_reg = STATUS;
//     unsigned char status_value;
//     int attempts = 0;
//     do {
//         if (write(i2c_fd, &status_reg, 1) != 1) return -2;
//         if (read(i2c_fd, &status_value, 1) != 1) return -3;
//         if (attempts++ > 100) {
//             fprintf(stderr, "Error: LIDAR busy timeout.\n");
//             return -4;
//         }
//         usleep(1000); 
//     } while (status_value & 0x01);

//     // 距離データ読み込み
//     unsigned char distance_reg = FULL_DELAY_HIGH;
//     unsigned char distance_buffer[2];
//     if (write(i2c_fd, &distance_reg, 1) != 1) return -5;
//     if (read(i2c_fd, distance_buffer, 2) != 2) return -6;

//     return (distance_buffer[0] << 8) | distance_buffer[1];
// }

// /**
//  * @brief ファイルから目標距離(m)を読み取る
//  */
// double read_target_position_m() {
//     FILE *fp = fopen(TARGET_POSITION_FILE, "r");
//     if (fp == NULL) {
//         return -1.0; 
//     }

//     double position_cm;
//     if (fscanf(fp, "%lf", &position_cm) != 1) {
//         fclose(fp);
//         return -2.0; 
//     }

//     fclose(fp);
//     return position_cm / 100.0; // cm -> m
// }

// void Handler(int signo)
// {
//     printf("\r\nHandler:Motor Stop\r\n");
//     Motor_Stop(MOTORA);
//     Motor_Stop(MOTORB);
//     if (i2c_fd >= 0) {
//         close(i2c_fd);
//     }
//     DEV_ModuleExit();
//     exit(0);
// }

// int main(void)
// {
//     // モジュールとモーターの初期化
//     if(DEV_ModuleInit()) exit(1);
//     Motor_Init();

//     // LIDARの初期化
//     if (init_lidar() != 0) {
//         DEV_ModuleExit();
//         exit(1);
//     }

//     signal(SIGINT, Handler);
//     printf("Starting low-frequency LIDAR control loop (1Hz)...\n");

//     // 時間管理用の変数
//     struct timespec last_measure_time;
//     clock_gettime(CLOCK_MONOTONIC, &last_measure_time);
    
//     int dist_cm = -1; // 最新の測定値を保持
//     const double STOP_TOLERANCE = 0.05; // 5cmの許容誤差
//     const double UPDATE_INTERVAL = 0.5; // 1.0sより安全な0.5s（2Hz）を推奨

//     while(1) {
//         struct timespec now;
//         clock_gettime(CLOCK_MONOTONIC, &now);

//         // 前回の測定から何秒経過したか計算
//         double elapsed = (now.tv_sec - last_measure_time.tv_sec) + 
//                          (now.tv_nsec - last_measure_time.tv_nsec) / 1e9;

//         // --- 指定時間ごとにLIDARの測定を実行 ---
//         if (elapsed >= UPDATE_INTERVAL) {
//             int new_dist = get_lidar_distance_cm();
//             if (new_dist > 0) {
//                 dist_cm = new_dist;
//                 last_measure_time = now; // 測定成功時のみタイマーリセット
//                 printf("[LIDAR] Updated Distance: %d cm\n", dist_cm);
//             } else {
//                 printf("[WARNING] Invalid data (0cm). Keeping last distance.\n");
//             }
//         }

//         // --- 目標距離の読み取りと制御ロジック ---
//         // double current_distance_m = (double)dist_cm / 100.0;
//         double target_distance_m = read_target_position_m();

//         if (target_distance_m >= 0 && dist_cm > 0) {
//             double current_distance_m = (double)dist_cm / 100.0;

//             // 目標より遠い (前進)
//             if (current_distance_m > target_distance_m + STOP_TOLERANCE) {
//                 Motor_Run(MOTORA, BACKWARD, MOVE_SPEED);
//                 Motor_Run(MOTORB, BACKWARD, MOVE_SPEED);
//             } 
//             // 目標より近い (後退)
//             else if (current_distance_m < target_distance_m - STOP_TOLERANCE) {
//                 Motor_Run(MOTORA, FORWARD, MOVE_SPEED);
//                 Motor_Run(MOTORB, FORWARD, MOVE_SPEED);
//             } 
//             // 範囲内 (停止)
//             else {
//                 Motor_Stop(MOTORA);
//                 Motor_Stop(MOTORB);
//             }
//         } else {
//             // 目標ファイルが読み込めない場合などは停止
//             Motor_Stop(MOTORA);
//             Motor_Stop(MOTORB);
//         }

//         // ループ自体の待機（0.1秒）。これにより目標ファイルの更新を素早くチェックできる
//         usleep(50 * 1000); 
//     }

//     // ここには到達しませんが、念のため
//     Handler(0);
//     return 0;
// }
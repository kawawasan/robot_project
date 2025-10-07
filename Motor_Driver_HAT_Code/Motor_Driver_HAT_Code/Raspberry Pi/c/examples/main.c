#include "main.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <time.h>

// --- LIDAR関連の定義 ---
const char* I2C_BUS_PATH = "/dev/i2c-1";
const int LIDAR_ADDRESS = 0x62;
const int ACQ_COMMAND = 0x00;
const int STATUS = 0x01;
const int FULL_DELAY_HIGH = 0x0f;

// --- 目標距離ファイル ---
const char* TARGET_POSITION_FILE = "/tmp/robot_target_position.txt";
const double DISTANCE_TOLERANCE = 0.05; // 5cmの誤差を許容

int i2c_fd = -1; // I2Cファイルディスクリプタ

/**
 * @brief LIDARの初期化
 * @return 0: 成功, -1: 失敗
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
 * @return 距離(cm)。エラー時は負の値。
 */
int get_lidar_distance_cm() {
    if (i2c_fd < 0) return -1;

    // 測定開始コマンド
    unsigned char write_buffer[2] = {ACQ_COMMAND, 0x04};
    if (write(i2c_fd, write_buffer, 2) != 2) {
        fprintf(stderr, "Error: Failed to write command to LIDAR.\n");
        return -1;
    }

    // ステータスがbusyでなくなるまで待つ
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
        usleep(1000); // 1ms待機
    } while (status_value & 0x01);

    // 距離データを読み込む
    unsigned char distance_reg = FULL_DELAY_HIGH;
    unsigned char distance_buffer[2];
    if (write(i2c_fd, &distance_reg, 1) != 1) return -5;
    if (read(i2c_fd, distance_buffer, 2) != 2) return -6;

    return (distance_buffer[0] << 8) | distance_buffer[1];
}

/**
 * @brief ファイルから目標距離(m)を読み取る
 * @return 目標距離(m)。ファイルがない/読めない場合は負の値。
 */
double read_target_position_m() {
    FILE *fp = fopen(TARGET_POSITION_FILE, "r");
    if (fp == NULL) {
        return -1.0; // ファイルなし
        // return 2.0 //モータの試験用
    }

    double position_cm;
    if (fscanf(fp, "%lf", &position_cm) != 1) {
        fclose(fp);
        return -2.0; // 読み取り失敗
    }

    fclose(fp);
    return position_cm / 100.0; // cmからmに変換
}

void  Handler(int signo)
{
    //System Exit
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
    //1.System Initialization
    if(DEV_ModuleInit())
        exit(1);
    
    //2.Motor Initialization
    Motor_Init();

    // 3. LIDAR初期化
    if (init_lidar() != 0) {
        DEV_ModuleExit();
        exit(1);
    }

    // Exception handling:ctrl + c
    signal(SIGINT, Handler);

    printf("Starting motor control loop...\n");

    while(1) {
        // 目標距離をファイルから取得
        double target_distance_m = read_target_position_m();

        // LIDARから現在距離を取得
        int dist_cm = get_lidar_distance_cm();
        if (dist_cm < 0) {
            fprintf(stderr, "Failed to read distance. Stopping motors.\n");
            Motor_Stop(MOTORA);
            Motor_Stop(MOTORB);
            usleep(200 * 1000); // 200ms待機
            continue;
        }
        double current_distance_m = (double)dist_cm / 100.0;

        if (target_distance_m >= 0) {
            // --- 目標距離が設定されている場合 ---
            // printf("Current: %.2f m, Target: %.2f m\n", current_distance_m, target_distance_m);

            // 目標より近ければ前進、遠ければ停止
            if (current_distance_m < target_distance_m - DISTANCE_TOLERANCE) {
                printf("Moving forward to target...\n");
                Motor_Run(MOTORA, BACKWARD, 50);
                Motor_Run(MOTORB, BACKWARD, 50);
            } else {
                printf("Target reached or passed. Stopping.\n");
                Motor_Stop(MOTORA);
                Motor_Stop(MOTORB);
            }
        } else {
            // --- 目標距離が設定されていない場合 (デフォルトの動作) ---
            // printf("Waiting for target position... Current distance: %.2f m\n", current_distance_m);
            // 安全のため停止
            Motor_Stop(MOTORA);
            Motor_Stop(MOTORB);
        }

        // 200ms待機
        usleep(200 * 1000);

    }

    //3.System Exit
    // この部分は通常到達しません
    Handler(0);
    DEV_ModuleExit();
    return 0;
}


// #include "main.h"

// void  Handler(int signo)
// {
//     //System Exit
//     printf("\r\nHandler:Motor Stop\r\n");
//     Motor_Stop(MOTORA);
//     Motor_Stop(MOTORB);
//     DEV_ModuleExit();

//     exit(0);
// }

// int main(void)
// {
//     //1.System Initialization
//     if(DEV_ModuleInit())
//         exit(0);
    
//     //2.Motor Initialization
//     Motor_Init();

//     printf("Motor_Run\r\n");
//     Motor_Run(MOTORA, FORWARD, 100);
//     Motor_Run(MOTORB, BACKWARD, 100);

//     // Exception handling:ctrl + c
//     signal(SIGINT, Handler);
//     while(1) {

//     }

//     //3.System Exit
//     DEV_ModuleExit();
//     return 0;
// }




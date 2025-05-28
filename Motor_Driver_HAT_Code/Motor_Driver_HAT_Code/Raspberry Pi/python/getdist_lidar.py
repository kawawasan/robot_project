# LIDARで1秒ごとに測距するプログラム
# coding: utf-8
#lider lite v3

import smbus  # type: ignore # type: ignore
import time  # type: ignore

try:
    bus = smbus.SMBus(1)  # Try bus 1 first
except OSError:
    print("Could not access I2C bus 1. Trying bus 0...")
    bus = smbus.SMBus(0)  # If bus 1 fails, try bus 0

address = 0x62  #Lider Lite v3のアドレス

ACQ_COMMAND = 0x00
STATUS = 0x01
FULL_DELAY_HIGH = 0x0f
FULL_DELAY_LOW = 0x10

def get_distance():
    bus.write_block_data(address,ACQ_COMMAND,[0x04])

    value = bus.read_byte_data(address, STATUS)
    while value & 0x01==1:
        value = bus.read_byte_data(address, STATUS)

    #16bitの測定距離をcm単位で取得する
    high = bus.read_byte_data(address, FULL_DELAY_HIGH)
    low = bus.read_byte_data(address,FULL_DELAY_LOW)
    val = (high << 8) + low
    dist = val
    dist_data = dist/100
    #print("Dist = {0} cm , {1} m".format(dist,dist_data))

    return dist_data

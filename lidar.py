# coding: utf-8
#lider lite v3

import smbus
import time

bus = smbus.SMBus(1)  #I2Cのバス番号
address = 0x62  #Lider Lite v3のアドレス

ACQ_COMMAND = 0x00
STATUS = 0x01
FULL_DELAY_HIGH = 0x0f
FULL_DELAY_LOW = 0x10

while True:
#0x00に0x04の内容を書き込む

     bus.write_block_data(address,ACQ_COMMAND,[0x04])

#0x01を読み込んで、最下位bitが0になるまで読み込む

     value = bus.read_byte_data(address, STATUS)
     while value & 0x01==1:
         value = bus.read_byte_data(address, STATUS)

#0x8fから2バイト読み込んで16bitの測定距離をcm単位で取得する

     high = bus.read_byte_data(address, FULL_DELAY_HIGH)
     low = bus.read_byte_data(address,FULL_DELAY_LOW)
     val = (high << 8) + low
     dist = val
     print("Dist = {0} cm , {1} m".format(dist,dist/100))

#cmを100倍してmに直す。

     time.sleep(1)

#time.sleep(1)で1秒ごとに距離を出力する。

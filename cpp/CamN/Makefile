# cpp_code
# ├── CamN
# │   ├── Makefile
# │   ├── object
# │   ├── source
# │   │   ├── mucvis_camn.cpp
# │   │   └── mucvis_camn_local.cpp
# │   └── .out
# └── include
#     ├── cpp
#     │   ├── bytequeue.cpp
#     │   ├── log.cpp
#     │   └── packet.cpp
#     ├── header
#     │   ├── bytequeue.h
#     │   ├── log.h
#     │   └── packet.h
#     └── object


# コンパイラ
CC = g++
# コンパイルオプション C++17規格でコンパイル
CFLAGS = -Wall -O3 -MMD -MP -std=c++17
# 実行ファイル名  make clean/all 用
TARGET = mucvis_camn_local.out
# コンパイル対象のソースコード
SRCDIR = source/
SRCS = $(wildcard $(SRCDIR)*.cpp)  # sourceディレクトリ内の全ての.cppファイルを取得
# SRCS = $(SRCDIR)mucvis_camn.cpp
SRCSTARGET = $(patsubst %.cpp,%.out,$(notdir $(SRCS)))

# インクルード.cppファイル
INCSRCDIR = ../include/cpp/
INCSRC = $(wildcard $(INCSRCDIR)*.cpp)  # include_cppディレクトリ内の全ての.cppファイルを取得

# オブジェクトファイル名
OBJDIR = object/
# OBJS = $(patsubst %.cpp,%.o,$(SRCS))
OBJS = $(TARGET:.out=.o)
OBJECTS = $(addprefix $(OBJDIR), $(notdir $(OBJS)))

# インクルードのオブジェクトファイル名
INCOBJDIR = ../include/object/
INCOBJS = $(patsubst %.cpp,%.o,$(INCSRC))
INCOBJECTS = $(addprefix $(INCOBJDIR), $(notdir $(INCOBJS)))

# 依存関係ファイル ヘッダファイル(.hpp)の更新を検知し更新
DEPENDS = $(OBJECTS:.o=.d)
INCDEPENDS = $(INCOBJECTS:.o=.d)

# インクルードファイルのあるディレクトリパス
INCDIR  =

# ライブラリファイルのあるディレクトリパス
LIBDIR  = 

# 追加するライブラリファイル
LIBS    = 


.PHONY: help  # "make help"でtarget一覧(.PHONY一覧)を出力
help:
	@grep "out:" Makefile | grep -v "grep" | awk '{print ($$1), " "$$(NF-1), ($$NF)}' | sed -e 's/://' -e 's/^/make /'
	@grep "^.PHONY:" Makefile | sed -e 's/.PHONY:/make/'
	@echo "TARGET = $(TARGET)"

# ターゲットファイル生成
# $(TARGET): $(OBJECTS) $(INCOBJECTS)
# 	$(CC) -o $@ $^ $(LIBDIR) $(LIBS)

mucvis_camn.out: $(OBJDIR)mucvis_camn.o $(INCOBJECTS)  # デフォルト
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_sleep_for.out: $(OBJDIR)mucvis_camn_sleep_for.o $(INCOBJECTS)  # デフォルト
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_sleep_until.out: $(OBJDIR)mucvis_camn_sleep_until.o $(INCOBJECTS)  # デフォルト
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_local.out: $(OBJDIR)mucvis_camn_local.o $(INCOBJECTS)  # ロール環境用
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_local_sleep_for.out: $(OBJDIR)mucvis_camn_local_sleep_for.o $(INCOBJECTS)  # ロール環境用_sleep_for使用
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"


mucvis_camn_time.out: $(OBJDIR)mucvis_camn_time.o $(INCOBJECTS)  # ロール環境用
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_multi_process.out: $(OBJDIR)mucvis_camn_multi_process.o $(INCOBJECTS)  # マルチプロセス版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread -lrt
	@echo "make $@"

mucvis_camn_g_mutex.out: $(OBJDIR)mucvis_camn_g_mutex.o $(INCOBJECTS)  # グローバルミューテックス版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_2class.out: $(OBJDIR)mucvis_camn_2class.o $(INCOBJECTS)  # 2クラス版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_noBlock_send.out: $(OBJDIR)mucvis_camn_noBlock_send.o $(INCOBJECTS)  # ノンブロッキング版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_priority.out: $(OBJDIR)mucvis_camn_priority.o $(INCOBJECTS)  # ソケットに優先順位をつけた版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_video_capture.out: $(OBJDIR)mucvis_camn_video_capture.o $(INCOBJECTS)  # カメラから映像を撮影する版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_video_capture_udp.out: $(OBJDIR)mucvis_camn_video_capture_udp.o $(INCOBJECTS)  # カメラから映像を撮影する版のUDP版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_udp.out: $(OBJDIR)mucvis_camn_udp.o $(INCOBJECTS)  # 映像としてダミーで他を送信するUDP版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_camn_video_capture_command.out: $(OBJDIR)mucvis_camn_video_capture_command.o $(INCOBJECTS)  # カメラから映像を撮影する．制御情報により宛先を変更する版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"


# オブジェクトファイル生成(.cppファイルから.oファイルを生成)
$(OBJDIR)%.o: $(SRCDIR)%.cpp
    # オブジェクトディレクトリがない時，作成
	@if [ ! -d $(OBJDIR) ]; then \
	echo "mkdir $(OBJDIR)"; mkdir -p $(OBJDIR); \
	fi
	$(CC) $(CFLAGS) -o $@ -c $<

# インクルードのオブジェクトファイル生成(.cppファイルから.oファイルを生成)
$(INCOBJDIR)%.o: $(INCSRCDIR)%.cpp
    # オブジェクトディレクトリがない時，作成
	@if [ ! -d $(INCOBJDIR) ]; then \
	echo "mkdir $(INCOBJDIR)"; mkdir -p $(INCOBJDIR); \
	fi
	$(CC) $(CFLAGS) -o $@ -c $<

# 依存関係ファイルをインクルード(ヘッダファイルの更新を検知し更新)
-include $(DEPENDS)
-include $(INCDEPENDS)


.PHONY: all  # "make all"で make cleanとmake TARGETを同時に実施。
all: clean $(TARGET)

.PHONY: clean  # 実行ファイルとobject/, include/object内のファイルを削除
clean:
	-rm -f $(OBJDIR)* $(INCOBJDIR)* $(TARGET)


# デバッグ: make -n で実行されるコマンドを確認(実行はしない)
# $(warning TARGET = $(TARGET))
# $(warning SRCS = $(SRCS))
# $(warning SRCSTARGET = $(SRCSTARGET))
# $(warning OBJS = $(OBJS))
# $(warning OBJECTS = $(OBJECTS))
# $(warning INCSRC = $(INCSRC))
# $(warning INCOBJS = $(INCOBJS))
# $(warning INCOBJECTS = $(INCOBJECTS))
# $(warning DEPENDS = $(DEPENDS))
# $(warning INCDEPENDS = $(INCDEPENDS))

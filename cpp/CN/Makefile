# cpp_code
# ├── CN
# │   ├── Makefile
# │   ├── object
# │   ├── source
# │   │   ├── mucvis_cn.cpp
# │   │   └── mucvis_cn_local.cpp
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
TARGET = mucvis_cn_local.out
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

mucvis_cn.out: $(OBJDIR)mucvis_cn.o $(INCOBJECTS)  # デフォルト
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_sleep_for.out: $(OBJDIR)mucvis_cn_sleep_for.o $(INCOBJECTS)  # デフォルト
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_local.out: $(OBJDIR)mucvis_cn_local.o $(INCOBJECTS)  # ロール環境用
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_video_save.out: $(OBJDIR)mucvis_cn_video_save.o $(INCOBJECTS)  # 映像をtsファイルとして保存
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_video_save_udp.out: $(OBJDIR)mucvis_cn_video_save_udp.o $(INCOBJECTS)  # 映像をtsファイルとして保存 UDP版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_video_save_play.out: $(OBJDIR)mucvis_cn_video_save_play.o $(INCOBJECTS)  # 映像をtsファイルとして保存し，名前付きパイプに渡してストリーミング再生
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_video_save_play_udp.out: $(OBJDIR)mucvis_cn_video_save_play_udp.o $(INCOBJECTS)  # 映像をtsファイルとして保存し，名前付きパイプに渡してストリーミング再生 UDP版
	$(CC) -o $@ $^ $(LIBDIR) $(LIBS) -pthread
	@echo "make $@"

mucvis_cn_video_save_play_command.out: $(OBJDIR)mucvis_cn_video_save_play_command.o $(INCOBJECTS)  # 映像をtsファイルとして保存し，名前付きパイプに渡してストリーミング再生．制御情報を入力可能
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

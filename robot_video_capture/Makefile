# ロボット撮影用プログラム

# コンパイラ
CC = g++
# コンパイルオプション
CFLAGS = -Wall -O3 -std=c++17
# 実行ファイル名
TARGET = capture_send.out save_recv.out
# コンパイル対象のソースコード
SRCDIR = source/
SRCS = $(wildcard $(SRCDIR)*.cpp)  # sourceディレクトリ内の全ての.cppファイルを取得
# SRCS = $(SRCDIR)mucvis_camn.cpp
SRCSTARGET = $(patsubst %.cpp,%.out,$(notdir $(SRCS)))

# インクルード.cppファイル
INCSRCDIR = 
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

capture_send.out: clean  # 撮影と送信を同時に行うプログラム
	$(CC) $(CFLAGS) -o $@ $(addprefix $(SRCDIR), $(@:.out=.cpp)) $(LIBDIR) $(LIBS) -lpthread
	@echo "make $@"

save_recv.out: clean  # 受信を行い，.tsファイルをmp4に変換するプログラム
	$(CC) $(CFLAGS) -o $@ $(addprefix $(SRCDIR), $(@:.out=.cpp)) $(LIBDIR) $(LIBS)
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

.PHONY: clean  # 実行ファイルを削除
clean:
	-rm -f $(TARGET)


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


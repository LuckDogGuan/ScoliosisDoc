CC = /home/guanjx/arm-rockchip830-linux-uclibcgnueabihf/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc
TARGET = instrument_app
CFLAGS += -std=c11 -D_POSIX_C_SOURCE=200809L -D_DEFAULT_SOURCE -Wall -Wextra -Werror -O2
CFLAGS += -Iinclude -Ithird_party/cjson

# 分类：app 主循环，net 发现与上传，capture 录像，storage 文件，audio 喇叭，board 按键灯电池，config 配置
SOURCES = \
	src/app/app_controller.c \
	src/config/config.c \
	src/net/wifi.c \
	src/net/upload.c \
	src/net/discover.c \
	src/storage/storage.c \
	src/audio/audio.c \
	src/capture/capture.c \
	src/board/battery.c \
	src/board/button.c \
	src/board/light.c \
	third_party/cjson/cJSON.c

all: $(TARGET)

$(TARGET): $(SOURCES) include/app.h include/config.h
	$(CC) $(CFLAGS) $(SOURCES) -o $@

check-host:
	$(MAKE) CC=gcc TARGET=instrument_app_host
	./instrument_app_host --check-config config.example.json
	python3 tests/test_upload.py
	python3 tests/test_pending_upload.py

.PHONY: all check-host

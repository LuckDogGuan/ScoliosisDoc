#!/bin/sh
set -eu
USB_FUNCTIONS_DIR=/sys/kernel/config/usb_gadget/rockchip/functions
USB_CONFIGS_DIR=/sys/kernel/config/usb_gadget/rockchip/configs/b.1
UVC_MULTI=off
configure_uvc_resolution_yuyv()
{
    UVC_DISPLAY_W=$1
    UVC_DISPLAY_H=$2
    UVC_DISPLAY_DIR=${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/uncompressed/u/${UVC_DISPLAY_W}_${UVC_DISPLAY_H}p
    mkdir ${UVC_DISPLAY_DIR}
    echo $UVC_DISPLAY_W > ${UVC_DISPLAY_DIR}/wWidth
    echo $UVC_DISPLAY_H > ${UVC_DISPLAY_DIR}/wHeight
    echo 333333 > ${UVC_DISPLAY_DIR}/dwDefaultFrameInterval
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMinBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMaxBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*2)) > ${UVC_DISPLAY_DIR}/dwMaxVideoFrameBufferSize
    echo -e "333333\n666666\n1000000\n2000000" > ${UVC_DISPLAY_DIR}/dwFrameInterval
}

configure_uvc_resolution_yuyv_720p()
{
    UVC_DISPLAY_W=$1
    UVC_DISPLAY_H=$2
    UVC_DISPLAY_DIR=${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/uncompressed/u/${UVC_DISPLAY_W}_${UVC_DISPLAY_H}p
    mkdir ${UVC_DISPLAY_DIR}
    echo $UVC_DISPLAY_W > ${UVC_DISPLAY_DIR}/wWidth
    echo $UVC_DISPLAY_H > ${UVC_DISPLAY_DIR}/wHeight
    echo 1000000 > ${UVC_DISPLAY_DIR}/dwDefaultFrameInterval
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMinBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMaxBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*2)) > ${UVC_DISPLAY_DIR}/dwMaxVideoFrameBufferSize
    echo -e "1000000\n2000000" > ${UVC_DISPLAY_DIR}/dwFrameInterval
}

configure_uvc_resolution_yuyv_1080p()
{
    UVC_DISPLAY_W=$1
    UVC_DISPLAY_H=$2
    UVC_DISPLAY_DIR=${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/uncompressed/u/${UVC_DISPLAY_W}_${UVC_DISPLAY_H}p
    mkdir ${UVC_DISPLAY_DIR}
    echo $UVC_DISPLAY_W > ${UVC_DISPLAY_DIR}/wWidth
    echo $UVC_DISPLAY_H > ${UVC_DISPLAY_DIR}/wHeight
    echo 2500000 > ${UVC_DISPLAY_DIR}/dwDefaultFrameInterval
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMinBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMaxBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*2)) > ${UVC_DISPLAY_DIR}/dwMaxVideoFrameBufferSize
    echo -e "2500000\n5000000" > ${UVC_DISPLAY_DIR}/dwFrameInterval
}

configure_uvc_resolution_mjpeg()
{
    UVC_DISPLAY_W=$1
    UVC_DISPLAY_H=$2
    UVC_DISPLAY_DIR=${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/mjpeg/m/${UVC_DISPLAY_W}_${UVC_DISPLAY_H}p
    mkdir ${UVC_DISPLAY_DIR}
    echo $UVC_DISPLAY_W > ${UVC_DISPLAY_DIR}/wWidth
    echo $UVC_DISPLAY_H > ${UVC_DISPLAY_DIR}/wHeight
    echo 333333 > ${UVC_DISPLAY_DIR}/dwDefaultFrameInterval
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMinBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*20)) > ${UVC_DISPLAY_DIR}/dwMaxBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*2)) > ${UVC_DISPLAY_DIR}/dwMaxVideoFrameBufferSize
    echo -e "333333\n666666\n1000000\n2000000" > ${UVC_DISPLAY_DIR}/dwFrameInterval
}
configure_uvc_resolution_h264()
{
    UVC_DISPLAY_W=$1
    UVC_DISPLAY_H=$2
    UVC_DISPLAY_DIR=${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/framebased/f1/${UVC_DISPLAY_W}_${UVC_DISPLAY_H}p
    mkdir ${UVC_DISPLAY_DIR}
    echo $UVC_DISPLAY_W > ${UVC_DISPLAY_DIR}/wWidth
    echo $UVC_DISPLAY_H > ${UVC_DISPLAY_DIR}/wHeight
    echo 333333 > ${UVC_DISPLAY_DIR}/dwDefaultFrameInterval
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*10)) > ${UVC_DISPLAY_DIR}/dwMinBitRate
    echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*10)) > ${UVC_DISPLAY_DIR}/dwMaxBitRate
    echo -e "333333\n400000\n500000\n666666\n1000000\n2000000" > ${UVC_DISPLAY_DIR}/dwFrameInterval
    echo -ne \\x48\\x32\\x36\\x34\\x00\\x00\\x10\\x00\\x80\\x00\\x00\\xaa\\x00\\x38\\x9b\\x71 > ${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/framebased/f1/guidFormat
}
configure_uvc_resolution_h265()
{
	UVC_DISPLAY_W=$1
	UVC_DISPLAY_H=$2
	UVC_DISPLAY_DIR=${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/framebased/f2/${UVC_DISPLAY_W}_${UVC_DISPLAY_H}p
	mkdir ${UVC_DISPLAY_DIR}
	echo $UVC_DISPLAY_W > ${UVC_DISPLAY_DIR}/wWidth
	echo $UVC_DISPLAY_H > ${UVC_DISPLAY_DIR}/wHeight
	echo 333333 > ${UVC_DISPLAY_DIR}/dwDefaultFrameInterval
	echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*10)) > ${UVC_DISPLAY_DIR}/dwMinBitRate
	echo $((UVC_DISPLAY_W*UVC_DISPLAY_H*10)) > ${UVC_DISPLAY_DIR}/dwMaxBitRate
	echo -e "333333\n400000\n500000\n666666" > ${UVC_DISPLAY_DIR}/dwFrameInterval
	echo -ne \\x48\\x32\\x36\\x35\\x00\\x00\\x10\\x00\\x80\\x00\\x00\\xaa\\x00\\x38\\x9b\\x71 > ${USB_FUNCTIONS_DIR}/$UVC_GS/streaming/framebased/f2/guidFormat
}

cdc_device_config()
{
	mkdir  ${USB_FUNCTIONS_DIR}/acm.g0
	CONFIG_STR=`cat /sys/kernel/config/usb_gadget/rockchip/configs/b.1/strings/0x409/configuration`
	STR=${CONFIG_STR}_acm
	echo $STR > ${USB_CONFIGS_DIR}/strings/0x409/configuration
	USB_CNT=`echo $STR | awk -F"_" '{print NF-1}'`
	let USB_CNT=USB_CNT+2
	if [ $UVC_MULTI = one ];then
	let USB_CNT=USB_CNT+1
	elif [ $UVC_MULTI = two ];then
	let USB_CNT=USB_CNT+2
	fi
	echo "acm on++++++ ${USB_CNT}"
	ln -s ${USB_FUNCTIONS_DIR}/acm.g0 ${USB_CONFIGS_DIR}/f${USB_CNT}
}


G=/sys/kernel/config/usb_gadget/rockchip
UVC_GS=uvc.gs1
F=$USB_FUNCTIONS_DIR/$UVC_GS
mkdir -p "$F"
printf 'ISG1321 USB Camera' > "$F/device_name"
printf 'ISG1321 USB Camera' > "$F/function_name"
echo 3072 > "$F/streaming_maxpacket"
echo 4 > "$F/uvc_num_request"
mkdir -p "$F/control/header/h"
ln -s "$F/control/header/h" "$F/control/class/fs/h"
ln -s "$F/control/header/h" "$F/control/class/ss/h"
mkdir -p "$F/streaming/mjpeg/m"
configure_uvc_resolution_mjpeg 1280 1080
configure_uvc_resolution_mjpeg 640 480
mkdir -p "$F/streaming/header/h"
ln -s "$F/streaming/mjpeg/m" "$F/streaming/header/h/m"
ln -s "$F/streaming/header/h" "$F/streaming/class/fs/h"
ln -s "$F/streaming/header/h" "$F/streaming/class/hs/h"
ln -s "$F/streaming/header/h" "$F/streaming/class/ss/h"
echo 0 > "$G/os_desc/use"
echo 0x0016 > "$G/idProduct"
echo 239 > "$G/bDeviceClass"
echo 2 > "$G/bDeviceSubClass"
echo 1 > "$G/bDeviceProtocol"
printf 'ISG1321 USB Camera' > "$G/strings/0x409/product"
echo uvc > "$USB_CONFIGS_DIR/strings/0x409/configuration"
ln -s "$F" "$USB_CONFIGS_DIR/f1"
UDC=$(ls /sys/class/udc | head -1)
echo "$UDC" > "$G/UDC"

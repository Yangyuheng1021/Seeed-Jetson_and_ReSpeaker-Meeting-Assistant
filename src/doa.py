# doa.py —— 读取 reSpeaker Flex 的 DoA（说话人方向角）与语音检测标志
# 协议实现参考官方 xvf_host.py（DOA_VALUE: resid=20, cmdid=18, uint16 x2）
# 已配置 udev 规则（/etc/udev/rules.d/99-respeaker.rules），普通用户免 sudo 访问
import struct

import usb.core
import usb.util

VID, PID = 0x2886, 0x001A          # 2 通道固件的 USB ID
DOA_RESID, DOA_CMDID = 20, 18      # DOA_VALUE 的 resid / cmdid
TIMEOUT_MS = 2000


class RespeakerDoA:
    """极简 DoA 读取器：只读 DOA_VALUE，无打印噪音。"""

    def __init__(self, vid=VID, pid=PID):
        self.dev = usb.core.find(idVendor=vid, idProduct=pid)
        if self.dev is None:
            raise RuntimeError(
                "找不到 reSpeaker Flex（2886:001a）。请检查 USB 连接，或运行 lsusb 确认设备存在。"
            )

    def read(self):
        """返回 (angle_0_359, speech_flag)。speech_flag=1 表示检测到语音。

        参考 xvf_host.py：wvalue = 0x80 | cmdid，windex = resid，
        读回 1 字节状态码 + 2 x uint16 数据。
        """
        resp = self.dev.ctrl_transfer(
            usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
            0,
            0x80 | DOA_CMDID,
            DOA_RESID,
            1 + 2 * 2,
            TIMEOUT_MS,
        )
        if resp[0] != 0:  # CONTROL_SUCCESS
            raise RuntimeError(f"设备返回异常状态码: {resp[0]}")
        angle, speech = struct.unpack("<HH", resp[1:5].tobytes())
        return angle, speech

    def close(self):
        usb.util.dispose_resources(self.dev)


if __name__ == "__main__":
    d = RespeakerDoA()
    try:
        for _ in range(5):
            a, s = d.read()
            print(f"DOA={a:3d}°  speech={s}")
    finally:
        d.close()

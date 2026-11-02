"""Pure playback clock: select saved samples; never change a saved pose."""
from bisect import bisect_right
import hashlib
import math


def checked_payload(payload, expected_sha256):
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('显示档案摘要不匹配，停止回放')
    return payload


class Timeline:
    def __init__(self, times):
        self.times = tuple(float(t) for t in times)
        if (not self.times or not all(math.isfinite(t) for t in self.times)
                or any(b <= a for a, b in zip(self.times, self.times[1:]))):
            raise ValueError('回放时间必须有限且严格递增')
        self.position = self.times[0]
        self.index = 0
        self.speed = 1.
        self.paused = True
        self.anchor = 0.

    def update(self, now):
        if not self.paused:
            self.position = min(self.times[-1], self.position + (now-self.anchor)*self.speed)
            self.anchor = now
            if self.position >= self.times[-1]:
                self.paused = True
        self.index = max(0, bisect_right(self.times, self.position)-1)
        return self.index

    def play(self, now):
        self.anchor = now
        self.paused = False

    def pause(self, now):
        self.update(now)
        self.paused = True

    def seek(self, seconds, now):
        self.position = max(self.times[0], min(self.times[-1], float(seconds)))
        self.anchor = now
        self.update(now)

    def restart(self, now):
        self.paused = True
        self.seek(self.times[0], now)

    def set_speed(self, speed, now):
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError('播放速度必须为正数')
        self.update(now)
        self.speed = speed
        self.anchor = now

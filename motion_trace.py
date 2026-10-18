# SPDX-License-Identifier: GPL-3.0-only
"""Bounded in-memory traces; no orientation integration or hardware diagnosis."""
from collections import deque
import math


def motion_vector(value):
    if not isinstance(value,list) or len(value)!=3:return None
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>10_000_000 for v in value):return None
    return tuple(value)


class MotionTrace:
    seconds = 10

    def __init__(self):
        self.samples=deque(maxlen=301)
        self.current=None
        self.last_time=self.advanced_at=self.ticks=None
        self.stalled=False

    def clear(self):
        self.samples.clear();self.current=None
        self.last_time=self.advanced_at=self.ticks=None;self.stalled=False

    def observe(self,motion,now):
        if not isinstance(motion,dict) or type(now) not in (int,float) or not math.isfinite(now):
            self.clear();return
        ticks=motion.get('sensor_ticks')
        if type(ticks) is not int or not 0<=ticks<2**32:self.clear();return
        if self.last_time is not None and (now<self.last_time or now-self.last_time>.5):self.clear()
        if self.ticks==ticks:
            self.last_time=now
            if now-self.advanced_at>.5:
                self.current=None;self.samples.clear();self.stalled=True
            return
        if self.ticks is not None and (ticks-self.ticks) % 2**32 > 2**31:self.clear()
        self.ticks=ticks;self.last_time=self.advanced_at=now;self.stalled=False
        values=(motion_vector(motion.get('gyro_dps')),motion_vector(motion.get('accel_g')))
        if self.current is not None and tuple(v is None for v in self.current)!=tuple(v is None for v in values):
            self.samples.clear()
        self.current=values
        self.samples.append((now,*values))
        while self.samples and now-self.samples[0][0]>self.seconds:self.samples.popleft()


def motion_demo(frame):
    """Explicit offline laboratory fixture; never a fallback for real input."""
    angle=frame/45
    return {'gyro_dps':[30*math.cos(angle),20*math.sin(angle),12*math.cos(angle/2)],
            'accel_g':[math.sin(angle)*.4,math.cos(angle)*.3,math.sqrt(1-(math.sin(angle)*.4)**2-(math.cos(angle)*.3)**2)],
            'gyro_raw':[0,0,0],'accel_raw':[0,0,0],'sensor_ticks':(frame*100000)%(2**32)}

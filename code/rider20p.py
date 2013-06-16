#
# Copyright (C) 2012  Per Myren
#
# This file is part of Bryton-GPS-Linux
#
# Bryton-GPS-Linux is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Bryton-GPS-Linux is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Bryton-GPS-Linux.  If not, see <http://www.gnu.org/licenses/>.
#

import warnings
import os
import array
import math
import re


import rider40

from utils import cached_property
from common import DataBuffer, TrackPoint, LogPoint, AvgMax




class FSReader(object):

    def __init__(self, dev_path, fs_path=None):
        self.dev_path = dev_path
        self.path = fs_path


    def open(self):

        if self.path is not None:
            return

        dev_path = os.path.realpath(self.dev_path)

        with open('/proc/mounts') as f:

            for line in f:
                line = line.split()

                if line[0] == dev_path:
                    self.path = line[1]
                    return
        raise RuntimeError('Failed to find the device mount point. '
                           'Try the -FS argument.')


    def close(self):
        pass

    def listdir(self, relpath):
        files = os.listdir(self.abs_path(relpath))
        return map(lambda x: self.rel_path(relpath, x), files)


    def open_file_buffer(self, filename):

        with open(self.abs_path(filename)) as f:
            data = f.read()
            return DataBuffer(None, array.array('B', data), data_len=len(data))



    def rel_path(self, path, filename):
        return os.path.join(path, filename)

    def abs_path(self, relpath):
        return os.path.join(self.path, relpath)



class Rider20p(object):

    has_altimeter = False

    def __init__(self, fs):
        self.fs = fs


    def read_serial(self):

        with open(self.fs.abs_path('device.ini')) as f:
            content = f.read()
            m = re.search(r'UUID=(\d+)', content)
            if m:
                return m.group(1)


    def open_file_buffer(self, filename):
        return self.fs.open_file_buffer(filename)

    def get_history_files(self):
        return filter(lambda x: x.endswith('.gal'),
                   self.fs.listdir('Data/History/GAL'))

    def open_trackpoint_file(self, id):
        return self.open_file_buffer('Data/History/TRK/{0}.trk'.format(id))

    def open_logpoint_file(self, id):
        return self.open_file_buffer('Data/History/SSL/{0}.ssl'.format(id))

    def open_summary_file(self, id):
        return self.open_file_buffer('Data/History/GAL/{0}.gal'.format(id))

    def read_storage_usage(self):

        st = os.statvfs(self.fs.path)

        ret = {}

        ret['total'] = {
            'total' : (st.f_blocks * st.f_frsize),
            'left' : (st.f_bavail * st.f_frsize)
        }

        return ret


class Track(rider40.Track):

    _id = None

    def __init__(self, device, id):
        super(Track, self).__init__(device)
        self._id = id


    @cached_property
    def trackpoints(self):

        buf = self.device.open_trackpoint_file(self._id)

        return _read_trackpoint_segments(buf)


    @cached_property
    def logpoints(self):

        buf = self.device.open_logpoint_file(self._id)

        return _read_logpoint_segments(buf)


    @cached_property
    def _read_summaries(self):

        buf = self.device.open_summary_file(self._id)

        buf.set_offset(128)

        laps = []

        if self.lap_count > 0:


            laps = self._read_laps(buf)

        summary = rider40._read_summary(buf)


        if laps and laps[-1].end < summary.end:
            laps.append(_calculate_last_lap(self, laps, summary))


        return rider40._read_summary(buf), laps



def read_history(device):

    files = device.get_history_files()
    files.sort()

    history = []

    for f in files:

        buf = device.open_file_buffer(f)

        timestamp = buf.uint32_from(0x10)
        name_len = buf.uint16_from(0x4e)

        _id = os.path.basename(f).split('.')[0]

        t = Track(device, _id)
        t.name = buf.str_from(0x58, name_len)
        t.timestamp = timestamp
        t.lap_count = buf.uint8_from(0x28)

        history.append(t)

    return history



def _read_trackpoint_segments(buf):

    segments = []

    buf.set_offset(16)

    while True:
        seg, next_offset = _read_trackpoint_segment(buf)

        segments.append(seg)

        if next_offset == 0xffffffff:
            break

        if buf.abs_offset + buf.rel_offset != next_offset:

            raise RuntimeError('Unexpected trackpoint segment offset')


    return segments



def _read_trackpoint_segment(buf):

    s = rider40.TrackPointSegment()
    s.point_size = 10

    s.timestamp = buf.uint32_from(0x00)
    seg_type = buf.uint8_from(0x1A)

    try:
        # seems to work with rider20plus
        s.segment_type = seg_type - 0x30
    except RuntimeError:
        # seems to work with rider21
        s.segment_type = seg_type - 0x40


    lon_start = buf.int32_from(0x04)
    lat_start = buf.int32_from(0x08)
    elevation_start = (buf.uint16_from(0x14) - 4000) / 4.0

    count = buf.uint32_from(0x20)

    if s.segment_type == rider40.SEGMENT_BEFORE_MOVING and count > 0:
        warnings.warn("Segment type {0} is not expected to "
                      "have any trackpoints".format(
                          rider40.SEGMENT_BEFORE_MOVING), RuntimeWarning)

    next_offset = buf.uint32_from(0x1c)


    format = buf.uint16_from(0x18)

    buf.set_offset(0x24)

    if count > 0 or lon_start != -1:

        if format == 0x0140:
            track_points = _read_trackpoints_format_1(buf, s.timestamp,
                                                      lon_start, lat_start,
                                                      elevation_start, count)
        elif format == 0x0440:
            track_points = _read_trackpoints_format_2(buf, s.timestamp,
                                                      lon_start, lat_start,
                                                      elevation_start, count)

        else:
            raise RuntimeError('Unknown trackpoint format. '
                               'It can probably easily be fixed if test data '
                               'is provided.')

        s.extend(track_points)

    return s, next_offset



def _read_trackpoints_format_1(buf, time, lon, lat, ele, count):

    track_points = []
    track_points.append(TrackPoint(
        timestamp=time,
        longitude=lon / 1000000.0,
        latitude=lat / 1000000.0,
        elevation=ele
    ))

    for i in range(count):

        time += buf.uint8_from(0x2)

        e = buf.int8_from(0x4) / 10.0
        if e < 0:
            e = math.ceil(e)
        else:
            e = math.floor(e)

        ele += e


        lon += buf.int16_from(0x06)
        lat += buf.int16_from(0x08)

        track_points.append(TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(10)


    return track_points



def _read_trackpoints_format_2(buf, time, lon, lat, ele, count):

    track_points = []
    track_points.append(TrackPoint(
        timestamp=time,
        longitude=lon / 1000000.0,
        latitude=lat / 1000000.0,
        elevation=ele
    ))

    for i in range(count):

        time += 4 *  buf.uint8_from(0x2)

        e = buf.int8_from(0x4) / 10.0
        if e < 0:
            e = math.ceil(e)
        else:
            e = math.floor(e)

        ele += e


        lon += buf.int16_from(0x06)
        lat += buf.int16_from(0x08)

        track_points.append(TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(10)


    return track_points



def _read_logpoint_segments(buf):

    buf.set_offset(16)

    segments = []

    while True:

        seg, next_offset = _read_logpoint_segment(buf)

        segments.append(seg)

        if next_offset == 0xffffffff:
            break

        if buf.abs_offset + buf.rel_offset != next_offset:

            raise RuntimeError('Unexpected logpoint offset')


    return segments



def _read_logpoint_segment(buf):

    s = rider40.LogPointSegment()

    s.timestamp = buf.uint32_from(0)


    # Not sure about the segment types, but it seems to be working
    try:
        s.segment_type = buf.uint8_from(0x0c) - 0xE0
    except RuntimeError, e:
        s.segment_type = buf.uint8_from(0x0c) - 0x40


    count = buf.uint16_from(0x0a)

    format = buf.uint16_from(0x08)

    next_offset = buf.uint32_from(0x4)

    buf.set_offset(0x10)

    if count > 0:

        if format == 0x4304:
            log_points = _read_logpoints_format_1(buf, s.timestamp, count)
            s.point_size = 3
        elif format == 0x7704:
            # It seems to be the same format as the rider40, but the
            # airpressure is instead the altitude
            # ((buf.uint16_from(0x05) - 4000) / 4.0)
            log_points = rider40._read_logpoints_format_3(buf, s.timestamp,
                                                          count)
            s.point_size = 8
        else:
            raise RuntimeError('Unknown logpoint format. '
                               'It can probably easily be fixed if test data '
                               'is provided.')

        s.extend(log_points)

    return s, next_offset



def _read_logpoints_format_1(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x0)
        speed = speed / 8.0 * 60 * 60 / 1000 if speed != 0xff else 0

        lp = LogPoint(
            timestamp=time,
            speed=speed,
        )

        log_points.append(lp)

        time += 4

        buf.set_offset(0x3)


    return log_points



def _calculate_last_lap(track, laps, summary):

    laps = laps[:]

    last_lap = ll = rider40.Summary()
    ll.start = laps[-1].end
    ll.end = summary.end
    ll.distance = summary.distance
    ll.ride_time = summary.ride_time
    ll.calories = summary.calories
    ll.altitude_gain = summary.altitude_gain
    ll.altitude_loss = summary.altitude_loss


    def _pop_lap():
        lap = l = laps.pop(0)
        ll.distance -= l.distance
        ll.ride_time = l.ride_time
        ll.calories -= l.calories
        ll.altitude_gain -= l.altitude_gain
        ll.altitude_loss -= l.altitude_loss
        return lap


    speed = []
    hr = []
    cadence = []

    lap = _pop_lap()

    for seg in track.merged_segments(remove_empty_track_segs=False):

        for tp, lp in seg:

            timestamp = tp.timestamp if tp is not None else lp.timestamp

            if timestamp > last_lap.start:
                if lp:
                    if lp.speed is not None and lp.speed > 0:
                        speed.append(lp.speed)
                    if lp.heartrate is not None and lp.heartrate > 0:
                        hr.append(lp.heartrate)
                    if lp.cadence is not None and lp.cadence > 0:
                        cadence.append(lp.cadence)

            elif timestamp <= lap.end:
                continue
            else:
                lap = _pop_lap()

    if speed:
        last_lap.speed = AvgMax(sum(speed) / len(speed), max(speed))
    else:
        last_lap.speed = AvgMax(0, 0)

    if hr:
        last_lap.heartrate = AvgMax(sum(hr) / len(hr), max(hr))
    if cadence:
        last_lap.cadence = AvgMax(sum(cadence) / len(cadence), max(cadence))

    return last_lap


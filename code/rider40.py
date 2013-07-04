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
import itertools

from utils import cached_property
from common import DataBuffer, TrackPoint, LogPoint, AvgMax


SEGMENT_BEFORE_MOVING = 0
SEGMENT_BEFORE_AUTOPAUSE = 1
SEGMENT_BEFORE_MANUALPAUSE = 2
SEGMENT_LAST = 3



class Rider40(object):

    READ_DATA = 0x10
    READ_SERIAL = 0x03

    BLOCK_SIZE = 4096
    BLOCK_COUNT = 0x1ff

    has_altimeter = True

    def __init__(self, device_access):
        self.dev = device_access


    def read_serial(self):

        data = self.dev.read_addr(0, block_count=4, read_type=self.READ_SERIAL)

        return data[-16:].tostring()


    def read_block(self, block_nr):

        if block_nr > self.BLOCK_COUNT:
            raise IOError('Reading past end of device.')

        return self.dev.read_addr(block_nr, 8, read_type=self.READ_DATA)


    def offset_to_block(self, offset):
        return offset / self.BLOCK_SIZE


    def read_from_offset(self, offset):

        d = self.read_block(self.offset_to_block(offset))

        rel_offset = offset % self.BLOCK_SIZE

        abs_offset = offset - rel_offset

        return DataBuffer(self, d, rel_offset, abs_offset)



    def read_storage_usage(self):


        l = self.last_log_entry

        tp_used = l.offset_end_trackpoints - l.offset_start_trackpoints

        lp_used = l.offset_end_logpoints - l.offset_start_logpoints

        tracklist_used = l.offset_end_history - l.offset_start_history

        laps_used = l.offset_end_laps - l.offset_start_laps


        ret = {}

        ret['trackpoints'] = {
            'total' : tp_used + l.space_left_trackpoints,
            'left' : l.space_left_trackpoints}
        ret['logpoints'] = {
            'total' : lp_used + l.space_left_logpoints,
            'left' : l.space_left_logpoints}
        ret['tracklist'] = {
            'total' : tracklist_used + l.space_left_history,
            'left' : l.space_left_history}
        ret['laps'] = {
            'total' : laps_used + l.space_left_laps,
            'left' : l.space_left_laps}

        return ret


    @cached_property
    def last_log_entry(self):

        buf = self.read_from_offset(0)

        for i in range(0x6000/256):

            if buf.uint16_from(0) == 0xffff:
                buf.set_offset(-256)
                break

            buf.set_offset(256)

        return _read_log_entry(buf)





class LogEntry(object):

    space_left_history = None
    offset_start_history = None
    offset_end_history = None

    space_left_laps = None
    offset_start_laps = None
    offset_end_laps = None

    space_left_trackpoints = None
    offset_start_trackpoints = None
    offset_end_trackpoints = None

    space_left_logpoints = None
    offset_start_logpoints = None
    offset_end_logpoints = None




class Track(object):

    name = None
    timestamp = None
    lap_count = None


    _offset_trackpoints = None
    _offset_summary = None
    _offset_laps = None


    def __init__(self, device):
        self.device = device


    @cached_property
    def trackpoints(self):

        buf = self.device.read_from_offset(
            self.device.last_log_entry.offset_start_trackpoints + \
                                           self._offset_trackpoints)

        return _read_trackpoint_segments(buf,
                    self.device.last_log_entry.offset_start_trackpoints)


    @cached_property
    def logpoints(self):
        buf = None
        segments = []
        for tseg in self.trackpoints:

            offset = self.device.last_log_entry.offset_start_logpoints + \
                    tseg._offset_logpoints


            if buf is None:
                buf = self.device.read_from_offset(offset)
            elif buf.abs_offset + buf.rel_offset != offset:
                warnings.warn('Unexpected logpoint offset.', RuntimeWarning)
                buf = self.device.read_from_offset(offset)


            seg = _read_logpoint_segment(buf)

            #
            #if seg.segment_type != tseg.segment_type:
            #    raise RuntimeError('Matching segments are expected to have'
            #                       ' the same type.')

            segments.append(seg)

        return segments


    @cached_property
    def summary(self):
        return self._read_summaries[0]


    @cached_property
    def lap_summaries(self):

        if self.lap_count == 0:
            return [self._read_summaries[0]]
        return self._read_summaries[1]


    @cached_property
    def settings(self):
        pass


    def merged_segments(self, remove_empty_track_segs=True):

        for tseg, lseg in zip(self.trackpoints, self.logpoints):

            if remove_empty_track_segs and not tseg:
                continue
            yield _merge_segments(tseg, lseg)


    @cached_property
    def _read_summaries(self):

        buf = None
        laps = []

        if self._offset_laps is not None:

            buf = self.device.read_from_offset(
                self.device.last_log_entry.offset_start_laps +
                                               self._offset_laps)
            laps = self._read_laps(buf)


        summary_offset = self.device.last_log_entry.offset_start_laps + \
                        self._offset_summary


        if buf is None or buf.rel_offset + buf.abs_offset != summary_offset:

            if buf is not None:
                warnings.warn('Unexpected summary offset', RuntimeWarning)

            buf = self.device.read_from_offset(
                self.device.last_log_entry.offset_start_laps +
                                               self._offset_summary)

        return _read_summary(buf), laps


    def _read_laps(self, buf):

        laps = []
        for i in range(self.lap_count):

            laps.append(_read_summary(buf))
            buf.set_offset(56)

        return laps


    @cached_property
    def storage_usage(self):

        tp = 0
        for seg in self.trackpoints:
            tp += 40
            if seg:
                tp += seg.point_size * len(seg)
        lp = 0
        for seg in self.logpoints:
            lp += 16
            if seg:
                lp += seg.point_size * len(seg)

        return dict(trackpoints=tp, logpoints=lp)




class Summary(object):

    start = None
    end = None
    distance = None

    speed = None
    heartrate = None
    cadence = None
    watts = None
    calories = None

    altitude_gain = None
    altitude_loss = None

    ride_time = None



class _Segment(object):


    point_size = None


    @property
    def segment_type(self):
        return self._segment_type


    @segment_type.setter
    def segment_type(self, value):
        if value not in self._SEGMENT_TYPES:
            raise RuntimeError('Unknown type ({0:x}) for {1}'.
                               format(value, self.__class__.__name__))
        self._segment_type = self._SEGMENT_TYPES.index(value)



class TrackPointSegment(list, _Segment):

    _SEGMENT_TYPES = (0, 1, 2, 3)

    timestamp = None
    _offset_logpoints = None
    point_size = 6



class LogPointSegment(list, _Segment):

    _SEGMENT_TYPES = (0x02, 0x06, 0x0A, 0x0E)

    timestamp = None



def read_history(device):


    buf = device.read_from_offset(device.last_log_entry.offset_start_history)

    end = device.last_log_entry.offset_end_history

    history = []

    while buf.abs_position < end:

        timestamp = buf.uint32_from(0x00)
        name_len = buf.uint16_from(0x26)

        if timestamp == 0xffffffff:
            # It's a planned trip
            buf.set_offset(0x30 + name_len)
            continue

        t = Track(device)
        t.name = buf.str_from(0x30, name_len)
        t.timestamp = timestamp
        t.lap_count = buf.uint8_from(0x18)
        # t._bike_type = buf.uint16_from(0x04)
        t._offset_trackpoints = buf.uint32_from(0x08)
        t._offset_summary = buf.uint32_from(0x0C)
        if t.lap_count > 0:
            t._offset_laps = buf.uint32_from(0x10)


        buf.set_offset(0x30 + name_len)

        history.append(t)

    return history


def _read_log_entry(buf):

    ui32 = buf.uint32_from
    l = LogEntry()

    l.space_left_history = ui32(0x58)
    l.offset_start_history = ui32(0x5C)
    l.offset_end_history = ui32(0x60)

    l.space_left_laps = ui32(0x64)
    l.offset_start_laps = ui32(0x68)
    l.offset_end_laps = ui32(0x6C)

    l.space_left_trackpoints = ui32(0x88)
    l.offset_start_trackpoints = ui32(0x8C)
    l.offset_end_trackpoints = ui32(0x90)

    l.space_left_logpoints = ui32(0x94)
    l.offset_start_logpoints = ui32(0x98)
    l.offset_end_logpoints = ui32(0x9C)

    return l


def _read_trackpoint_segments(buf, trackpoints_offset):

    segments = []

    while True:
        seg, next_offset = _read_trackpoint_segment(buf)

        segments.append(seg)

        # Usually the last segment have segment type SEGMENT_LAST,
        # but sometimes this is not true, so we also check that
        # if "next_offset" is 0xffffffff it was probably the last segment.
        if seg.segment_type == SEGMENT_LAST or next_offset == 0xffffffff:
            break


        next_offset += trackpoints_offset

        # Sometimes is seems like an extra trackpoint is added
        # to a segment but is not included in the count in the segment.
        # We have to check this and skip some bytes if necessary.
        if buf.abs_offset + buf.rel_offset != next_offset:

            diff = next_offset - buf.abs_offset - buf.rel_offset
            if diff > 6:
                warnings.warn('Bigger than expected diff between segment '
                              'offsets.', RuntimeWarning)
            if diff < 0:
                warnings.warn('Unexpected negative diff between segment '
                              'offsets.', RuntimeWarning)
            buf.set_offset(diff)


    return segments


def _read_trackpoint_segment(buf):

    s = TrackPointSegment()

    s.timestamp = buf.uint32_from(0x00)
    s.segment_type = buf.uint8_from(0x1A)

    lon_start = buf.int32_from(0x04)
    lat_start = buf.int32_from(0x08)
    elevation_start = (buf.uint16_from(0x14) - 4000) / 4.0

    count = buf.uint32_from(0x20)

    s._offset_logpoints = buf.uint32_from(0x24)

    if s.segment_type == SEGMENT_BEFORE_MOVING and count > 0:
        warnings.warn("Segment type {0} is not expected to "
                      "have any trackpoints".format(SEGMENT_BEFORE_MOVING),
                      RuntimeWarning)

    next_offset = buf.uint32_from(0x1c)


    format = buf.uint16_from(0x18)

    buf.set_offset(0x28)

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

        time += buf.uint8_from(0) / 4
        ele += buf.int8_from(0x1) / 10.0
        lon += buf.int16_from(0x02)
        lat += buf.int16_from(0x04)

        track_points.append(TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(0x6)


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

        time += buf.uint8_from(0)
        ele += buf.int8_from(0x1) / 10.0
        lon += buf.int16_from(0x02)
        lat += buf.int16_from(0x04)

        track_points.append(TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(0x6)


    return track_points



def _read_logpoint_segment(buf):

    s = LogPointSegment()

    s.timestamp = buf.uint32_from(0)
    s.segment_type = buf.uint8_from(0x0c)

    count = buf.uint16_from(0x0a)

    format = buf.uint16_from(0x08)

    buf.set_offset(0x10)

    if count > 0:

        if format == 0x7104:
            log_points = _read_logpoints_format_1(buf, s.timestamp, count)
            s.point_size = 6
        elif format == 0x7504:
            log_points = _read_logpoints_format_2(buf, s.timestamp, count)
            s.point_size = 7
        elif format == 0x7704:
            log_points = _read_logpoints_format_3(buf, s.timestamp, count)
            s.point_size = 8
        else:
            raise RuntimeError('Unknown logpoint format. You are probably '
                               'using a sensor that has not been tested '
                               'during development. Maybe a powermeter.'
                               'It can probably easily be fixed if test data '
                               'is provided.')

        s.extend(log_points)

    return s



def _read_logpoints_format_1(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        speed = speed / 8.0 * 60 * 60 / 1000 if speed != 0xff else 0

        lp = LogPoint(
            timestamp=time,
            speed=speed,
            temperature=buf.int16_from(0x01) / 10.0,
            airpressure=buf.uint16_from(0x03) * 2.0
        )

        log_points.append(lp)

        time += 4

        buf.set_offset(0x6)


    return log_points



def _read_logpoints_format_2(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        speed = speed / 8.0 * 60 * 60 / 1000 if speed != 0xff else 0

        lp = LogPoint(
            timestamp=time,
            speed=speed,
            temperature=buf.int16_from(0x02) / 10.0,
            airpressure=buf.uint16_from(0x04) * 2.0
        )

        hr = buf.uint8_from(0x01)
        if hr != 0xff:
            lp.heartrate = hr


        log_points.append(lp)

        time += 4

        buf.set_offset(0x7)


    return log_points



def _read_logpoints_format_3(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        speed = speed / 8.0 * 60 * 60 / 1000 if speed != 0xff else 0

        lp = LogPoint(
            timestamp=time,
            speed=speed,
            temperature=buf.int16_from(0x03) / 10.0,
            airpressure=buf.uint16_from(0x05) * 2.0
        )

        cad = buf.uint8_from(0x01)
        if cad != 0xff:
            lp.cadence = cad

        hr = buf.uint8_from(0x02)
        if hr != 0xff:
            lp.heartrate = hr

        log_points.append(lp)

        time += 4

        buf.set_offset(0x8)


    return log_points



def _read_summary(buf):

    s = Summary()

    s.start = buf.uint32_from(0x00)
    s.end = buf.uint32_from(0x04)
    s.distance = buf.uint32_from(0x08)

    s.speed = AvgMax(
        buf.uint8_from(0x0c) / 8.0 * 60 * 60 / 1000,
        buf.uint8_from(0x0d) / 8.0 * 60 * 60 / 1000,
    )

    s.heartrate = AvgMax(
        buf.uint8_from(0x0e) if buf.uint8_from(0x0e) != 0xff else 0,
        buf.uint8_from(0x0f) if buf.uint8_from(0x0f) != 0xff else 0,
    )

    s.cadence = AvgMax(
        buf.uint8_from(0x10) if buf.uint8_from(0x10) != 0xff else 0,
        buf.uint8_from(0x11) if buf.uint8_from(0x11) != 0xff else 0,
    )

    # s.watts = AvgMax(
    #     buf.uint8_from(0x12),
    #     buf.uint8_from(0x13),
    # )

    s.altitude_gain = buf.uint16_from(0x16)
    s.altitude_loss = buf.uint16_from(0x18)
    s.calories = buf.uint16_from(0x1a)
    s.ride_time = buf.uint32_from(0x1c)

    return s



def _merge_segments(track_seg, log_seg):
    """
    The trackpoints and logpoints doesn't allways have the same timestamp.
    This function will try to merge the points which have the closest
    timestamp to eachother. Points are only merged if they are 2 or less
    seconds apart.

    This current implementation is quite ugly.

    Here is a short explanation:

    The two segments are merged into one list and sorted by timestamp.
    Then 4 items at the time are compared.

    The 3 first items are potentialy merged, the last is just used
    to check that the last to are not equal.

    The items which are closest together out of (0 and 1) or (1 and 2)
    are merged. If (1 and 2) are closest 0 is returned alone.
    """

    def _point(a, b):

        if type(a) == type(b):
            raise RuntimeError("Can not merge logpoint/trackpoint of same type."
                               " This should not happend, it's a bug in the code.")

        if isinstance(a, TrackPoint):
            return (a, b)
        elif isinstance(b, TrackPoint) or b is None:
            return (b, a)
        return (a, b)

    items = sorted(itertools.chain(track_seg, log_seg),
                   key=lambda x: x.timestamp)

    l = items[0:4]
    count = i = len(l)
    while count > 1:

        if l[0].timestamp == l[1].timestamp:
            if type(l[0]) == type(l[1]):
                yield _point(l.pop(0), None)
            else:
                yield _point(l.pop(0), l.pop(0))
        elif l[1].timestamp - l[0].timestamp > 2:
            yield _point(l.pop(0), None)
        elif type(l[0]) == type(l[1]):
            yield _point(l.pop(0), None)
        elif count > 2 and type(l[1]) == type(l[2]):
            yield _point(l.pop(0), l.pop(0))
        elif count > 3 and l[2].timestamp == l[3].timestamp:
            yield _point(l.pop(0), l.pop(0))
        elif count > 2:
            diff1 = l[1].timestamp - l[0].timestamp
            diff2 = l[2].timestamp - l[1].timestamp
            if diff1 > diff2:
                yield _point(l.pop(0), None)
                yield _point(l.pop(0), l.pop(0))
            else:
                yield _point(l.pop(0), l.pop(0))
        else:
            if l[1].timestamp - l[0].timestamp <= 2:
                yield _point(l.pop(0), l.pop(0))
            else:
                yield _point(l.pop(0), None)
                yield _point(l.pop(0), None)

        more = 4 - len(l)
        l.extend(items[i:i + more])  # Add back as many as was removed
        i += more
        count = len(l)

    if l:
        yield _point(l[0], None)




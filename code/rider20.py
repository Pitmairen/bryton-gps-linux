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

import rider40

from utils import cached_property
from common import AvgMax


OFFSET_TRACKPOINTS = 0x36000 + 24
OFFSET_LOGPOINTS = 0xAE000 + 24
OFFSET_SUMMARIES = 0x11000
OFFSET_TRACKLIST = 0x8e94



class Rider20(rider40.Rider40):

    BLOCK_COUNT = 0x0ff

    has_altimeter = False

    TRACKPOINT_SPACE = 286696
    LOGPOINTS_SPACE = 278504
    TRACKLIST_SPACE = 33072
    LAPS_SPACE = 114688


class Track(rider40.Track):


    @cached_property
    def trackpoints(self):

        buf = self.device.read_from_offset(OFFSET_TRACKPOINTS +
                                           self._offset_trackpoints)

        return _read_trackpoint_segments(buf)


    @cached_property
    def logpoints(self):
        buf = None
        segments = []
        for tseg in self.trackpoints:

            offset = OFFSET_LOGPOINTS + tseg._offset_logpoints


            if buf is None:
                buf = self.device.read_from_offset(offset)
            elif buf.abs_offset + buf.rel_offset != offset:
                warnings.warn('Unexpected logpoint offset.', RuntimeWarning)
                buf = self.device.read_from_offset(offset)


            seg = _read_logpoint_segment(buf)

            if seg.segment_type != tseg.segment_type:
                raise RuntimeError('Matching segments are expected to have'
                                   ' the same type.')

            segments.append(seg)

        return segments


    @cached_property
    def _read_summaries(self):

        buf = None
        laps = []

        if self._offset_laps is not None:

            buf = self.device.read_from_offset(OFFSET_SUMMARIES +
                                               self._offset_laps)
            laps = self._read_laps(buf)

        summary_offset = OFFSET_SUMMARIES + self._offset_summary

        if buf is None or buf.rel_offset + buf.abs_offset != summary_offset:

            if buf is not None:
                warnings.warn('Unexpected summary offset', RuntimeWarning)

            buf = self.device.read_from_offset(OFFSET_SUMMARIES +
                                               self._offset_summary)

        summary = rider40._read_summary(buf)

        if laps and laps[-1].end < summary.end:
            laps.append(_calculate_last_lap(self, laps, summary))

        return summary, laps


    def _read_laps(self, buf):

        laps = []
        for i in range(self.lap_count):

            laps.append(rider40._read_summary(buf))
            buf.set_offset(32)

        return laps





def read_history(device):

    buf = device.read_from_offset(OFFSET_TRACKLIST)

    count = buf.uint16_from(0x08)

    if count == 0xffff:
        count = 0

    buf.set_offset(24)

    history = []

    for i in range(count):

        t = Track(device)
        t.timestamp = buf.uint32_from(0x00)
        t.name = buf.str_from(0x04, 16)  # hardcoded length

        t._offset_trackpoints = buf.uint32_from(0x88)

        t.lap_count = buf.uint8_from(0x94)
        t._offset_summary = buf.uint32_from(0x8c)
        if t.lap_count > 0:
            t._offset_laps = buf.uint32_from(0x90)


        history.append(t)

        buf.set_offset(156)

    return history



def _read_trackpoint_segments(buf):

    segments = []

    while True:
        seg, next_offset = _read_trackpoint_segment(buf)

        segments.append(seg)

        # if seg.segment_type == SEGMENT_LAST:
        #     break
        if next_offset == 0xffffffff:
            break


        next_offset += OFFSET_TRACKPOINTS

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

    s = rider40.TrackPointSegment()

    s.timestamp = buf.uint32_from(0x00)
    s.segment_type = buf.uint8_from(0x1A)

    lon_start = buf.int32_from(0x04)
    lat_start = buf.int32_from(0x08)
    elevation_start = (buf.uint16_from(0x14) - 4000) / 4.0

    count = buf.uint32_from(0x20)

    s._offset_logpoints = buf.uint32_from(0x24)

    next_offset = buf.uint32_from(0x1c)

    format = buf.uint16_from(0x18)

    buf.set_offset(0x28)

    if count > 0 or lon_start != -1:

        if format in [0x0160, 0x0161]:
            track_points = _read_trackpoints_format_1(buf, s.timestamp,
                                                      lon_start, lat_start,
                                                      elevation_start, count)
        elif format in [0x0461, 0x0460]:
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
    track_points.append(rider40.TrackPoint(
        timestamp=time,
        longitude=lon / 1000000.0,
        latitude=lat / 1000000.0,
        elevation=ele
    ))

    for i in range(count):

        time += buf.uint8_from(0x5)

        cur_ele = buf.int8_from(0x4)
        if cur_ele != -1 and cur_ele != 0:
            ele = (cur_ele - 10) * 10.0

        lon += buf.int16_from(0x00)
        lat += buf.int16_from(0x02)

        track_points.append(rider40.TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(0x6)

    _smooth_elevation(track_points)

    return track_points



def _read_trackpoints_format_2(buf, time, lon, lat, ele, count):

    track_points = []
    track_points.append(rider40.TrackPoint(
        timestamp=time,
        longitude=lon / 1000000.0,
        latitude=lat / 1000000.0,
        elevation=ele
    ))

    for i in range(count):

        time_val = buf.uint8_from(0x5)
        if time_val != 1:
            warnings.warn('Unexpected time value in trackpoint format. '
                          'Test data is needed to verify if this value is correct.',
                          RuntimeWarning)

        time += 4 * time_val

        cur_ele = buf.int8_from(0x4)
        if cur_ele != -1 and cur_ele != 0:
            ele = (cur_ele - 10) * 10.0

        lon += buf.int16_from(0x00)
        lat += buf.int16_from(0x02)

        track_points.append(rider40.TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(0x6)

    _smooth_elevation(track_points)

    return track_points



def _read_logpoint_segment(buf):

    s = rider40.LogPointSegment()

    s.timestamp = buf.uint32_from(0)
    s.segment_type = buf.uint8_from(0x0c)

    count = buf.uint16_from(0x0a)

    format = buf.uint16_from(0x08)

    buf.set_offset(0x10)

    if count > 0:

        if format in [0x8104, 0x0104]:
            log_points = _read_logpoints_format_1(buf, s.timestamp, count)
            s.point_size = 1
        elif format in [0x8704, 0x0704]:
            log_points = _read_logpoints_format_2(buf, s.timestamp, count)
            s.point_size = 3
        elif format in [0x0304, 0x8304]:
            log_points = _read_logpoints_format_3(buf, s.timestamp, count)
            s.point_size = 2
        elif format in [0x0504, 0x8504]:
            log_points = _read_logpoints_format_4(buf, s.timestamp, count)
            s.point_size = 2
        else:
            raise RuntimeError('Unknown logpoint format. You are probably '
                               'using a sensor that has not been tested '
                               'during development. '
                               'It can probably easily be fixed if test data '
                               'is provided.')

        s.extend(log_points)

    return s



def _read_logpoints_format_1(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        if speed != 0xff:
            speed = speed / 8.0 * 60 * 60 / 1000
        else:
            speed = None

        lp = rider40.LogPoint(
            timestamp=time,
            speed=speed,
        )

        log_points.append(lp)

        time += 4

        buf.set_offset(0x1)


    return log_points



def _read_logpoints_format_2(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        if speed != 0xff:
            speed = speed / 8.0 * 60 * 60 / 1000
        else:
            speed = None

        lp = rider40.LogPoint(
            timestamp=time,
            speed=speed,
        )

        cad = buf.uint8_from(0x01)
        if cad != 0xff:
            lp.cadence = cad

        hr = buf.uint8_from(0x02)
        if hr != 0xff:
            lp.heartrate = hr

        log_points.append(lp)

        time += 4

        buf.set_offset(0x03)


    return log_points



def _read_logpoints_format_3(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        if speed != 0xff:
            speed = speed / 8.0 * 60 * 60 / 1000
        else:
            speed = None

        lp = rider40.LogPoint(
            timestamp=time,
            speed=speed,
        )

        cad = buf.uint8_from(0x01)
        if cad != 0xff:
            lp.cadence = cad

        log_points.append(lp)

        time += 4

        buf.set_offset(0x02)


    return log_points



def _read_logpoints_format_4(buf, time, count):

    log_points = []

    for i in range(count):

        speed = buf.uint8_from(0x00)
        if speed != 0xff:
            speed = speed / 8.0 * 60 * 60 / 1000
        else:
            speed = None

        lp = rider40.LogPoint(
            timestamp=time,
            speed=speed,
        )

        hr = buf.uint8_from(0x01)
        if hr != 0xff:
            lp.heartrate = hr

        log_points.append(lp)

        time += 4

        buf.set_offset(0x02)


    return log_points



def _smooth_elevation(track_points):

    ele_stack = []
    for p in track_points:

        ele_stack.append(p.elevation)

        if len(ele_stack) == 30:
            p.elevation = sum(ele_stack) / 30
            ele_stack.pop(0)
        else:
            p.elevation = sum(ele_stack) / len(ele_stack)



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



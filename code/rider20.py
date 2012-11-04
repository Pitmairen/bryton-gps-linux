
import warnings

import rider40

from utils import cached_property



OFFSET_TRACKPOINTS = 0x36000 + 24
OFFSET_LOGPOINTS = 0xAE000 + 24
OFFSET_SUMMARIES = 0x11000
OFFSET_TRACKLIST = 0x8e94



class Rider20(rider40.Rider40):

    BLOCK_COUNT = 0x0ff



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
    def summary(self):
        buf = self.device.read_from_offset(OFFSET_SUMMARIES +
                                           self._offset_summary)
        return rider40._read_summary(buf)



def read_history(device):

    buf = device.read_from_offset(OFFSET_TRACKLIST)

    count = buf.uint16_from(0x08)

    buf.set_offset(24)

    history = []

    for i in range(count):

        t = Track(device)
        t.timestamp = buf.uint32_from(0x00)
        t.name = buf.str_from(0x04, 16) # hardcoded length

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
    if format != 0x0161 and (count == 0 and format not in [0x0140, 0x0141]):
        raise RuntimeError('Unknown trackpoint format. '
                           'It can probably easily be fixed if test data '
                           'is provided.')

    buf.set_offset(0x28)

    if count > 0:
        s.extend(_read_trackpoints(buf, s.timestamp, lon_start, lat_start,
                                   elevation_start, count))

    return s, next_offset



def _read_trackpoints(buf, time, lon, lat, ele, count):

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



def _read_logpoint_segment(buf):

    s = rider40.LogPointSegment()

    s.timestamp = buf.uint32_from(0)
    s.segment_type = buf.uint8_from(0x0c)

    count = buf.uint16_from(0x0a)

    format = buf.uint16_from(0x08)

    buf.set_offset(0x10)

    if count > 0:

        if format in [0x8104, 0x0104]:
            log_points = _read_logpoints(buf, s.timestamp, count)
        else:
            raise RuntimeError('Unknown logpoint format. You are probably '
                               'using a sensor that has not been tested '
                               'during development. '
                               'It can probably easily be fixed if test data '
                               'is provided.')

        s.extend(log_points)

    return s



def _read_logpoints(buf, time, count):

    log_points = []

    for i in range(count):

        lp = rider40.LogPoint(
            timestamp=time,
            speed=buf.uint8_from(0x00) / 8.0 * 60 * 60 / 1000,
        )

        log_points.append(lp)

        time += 4

        buf.set_offset(0x1)


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



#
# Copyright (C) 2013  Per Myren
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
import calendar
import time
import sqlite3

from contextlib import closing

from xml.etree import cElementTree as xml

import rider40

from utils import cached_property
from common import DataBuffer, TrackPoint, LogPoint, AvgMax


DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

SUPPORTED_FROMATS = set(['GH1.4.0.56'])


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

    def read_file(self, filename):

        with open(self.abs_path(filename)) as f:
            return f.read()

    def rel_path(self, path, filename):
        return os.path.join(path, filename)

    def abs_path(self, relpath):
        return os.path.join(self.path, relpath)



class Rider50(object):

    has_altimeter = True

    def __init__(self, fs):
        self.fs = fs


    def read_serial(self):
        with open(self.fs.abs_path('Device.ini')) as f:
            content = f.read()
            m = re.search(r'UUID=(\d+)', content)
            if m:
                return m.group(1)

    def open_file_buffer(self, filename):
        return self.fs.open_file_buffer(filename)

    def get_history_files(self):
        return filter(lambda x: x.endswith('-STA.xml'),
               self.fs.listdir('thalia/applications/CYCLING/DATA/TRACELOG'))

    def open_trackpoint_file(self, id):
        return self.open_file_buffer(
            'thalia/applications/CYCLING/DATA/TRACELOG/{0}-GPS.dat'.format(id))

    def open_logpoint_file(self, id):
        return self.open_file_buffer(
            'thalia/applications/CYCLING/DATA/TRACELOG/{0}-TRN.dat'.format(id))

    def open_summary_file(self, id):
        return self.fs.read_file(
            'thalia/applications/CYCLING/DATA/TRACELOG/{0}-STA.xml'.format(id))

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

        data = self.device.open_summary_file(self._id)

        return _read_summaries(data)




def read_history(device):

    db = device.fs.abs_path('thalia/applications/CYCLING/DATA/ROUTE/route.dat')

    if not os.path.exists(db):
        raise RuntimeError('Tracelog database file not found. (Tried: "{}")'.format(db))

    log = []

    with sqlite3.connect(db) as con:

        with closing(con.cursor()) as c:

            c.execute('SELECT idRoute, Title, CreateTime FROM TraceLog ' \
                      'ORDER BY idRoute ASC')

            log = c.fetchall()


    history = []

    for id, name, time in log:

        t = Track(device, id)
        t.name = name
        t.timestamp = time
        t.lap_count = 0

        history.append(t)

    return history



def _str_to_timestamp(datetime_str):

    return int(calendar.timegm(time.strptime(datetime_str, DATE_FORMAT)))


def _read_summaries(xml_content):

    s = rider40.Summary()

    data = xml.fromstring(xml_content)
    data = data.find('summary')

    s.start = _str_to_timestamp(data.get('start'))
    s.end = _str_to_timestamp(data.get('end'))

    s.distance = float(data.find('distance').text)


    speed = data.find('speed')
    s.speed = AvgMax(
        float(speed.get('avg', 0)),
        float(speed.get('max', 0)))

    hr = data.find('hrm')
    s.heartrate = AvgMax(
        int(hr.get('avg', 0)),
        int(hr.get('max', 0)))

    cad = data.find('cad')
    s.cadence = AvgMax(
        int(cad.get('avg', 0)),
        int(cad.get('max', 0)))


    s.altitude_gain = float(data.find('altgain').text)
    s.altitude_loss = float(data.find('altloss').text)
    s.calories = int(float(data.find('calorie').text))
    s.ride_time = int(float(data.find('rtime').text))

    return s, []






def _read_trackpoint_segments(buf):

    if buf.str_from(0, 9) != 'gps track':
        raise RuntimeError('Unexpected trackpoint fileformat')

    version = buf.str_from(0x20, 10)
    if version not in SUPPORTED_FROMATS:
        warnings.warn('Untested gps file format.', RuntimeWarning)


    segments = []

    timestamp = buf.uint32_from(0x18)

    buf.set_offset(0x30)

    while True:
        seg = _read_trackpoint_segment(buf, timestamp)

        segments.append(seg)

        break

    return segments



def _read_trackpoint_segment(buf, start_timestamp):

    s = rider40.TrackPointSegment()
    s.point_size = 20

    s.timestamp = start_timestamp
    s.segment_type = 0

    count = buf.uint32_from(0)

    buf.set_offset(4)

    if count > 0:

        track_points = _read_trackpoints(buf, s.timestamp, count)

        s.extend(track_points)

    return s



def _read_trackpoints(buf, start_time, count):

    track_points = []

    for i in range(count):

        time = start_time + buf.be_uint32_from(16)

        lon = buf.be_int32_from(0)
        lat = buf.be_int32_from(4)
        ele = buf.be_int16_from(8) / 10.0

        # buf.be_int16_from(10) # magnetic variation

        track_points.append(TrackPoint(
            timestamp=time,
            longitude=lon / 1000000.0,
            latitude=lat / 1000000.0,
            elevation=ele
        ))


        buf.set_offset(20)

    return track_points





def _read_logpoint_segments(buf):


    if buf.str_from(0, 12) != 'sensor value':
        raise RuntimeError('Unexpected logpoint fileformat')

    version = buf.str_from(0x20, 10)
    if version not in SUPPORTED_FROMATS:
        warnings.warn('Untested log file format.', RuntimeWarning)


    segments = []

    timestamp = buf.uint32_from(0x18)

    buf.set_offset(0x30)

    while True:
        seg = _read_logpoint_segment(buf, timestamp)

        segments.append(seg)

        break

    return segments



def _read_logpoint_segment(buf, start_timestamp):

    s = rider40.LogPointSegment()

    s.point_size = 22
    s.timestamp = start_timestamp

    s.segment_type = 0x02

    count = buf.uint32_from(0)

    buf.set_offset(4)

    if count > 0:

        log_points = _read_logpoints(buf, s.timestamp, count)

        s.extend(log_points)

    return s



def _read_logpoints(buf, start_time, count):

    log_points = []

    for i in range(count):

        time = start_time + buf.be_uint32_from(0)

        speed = buf.be_uint16_from(20)
        speed = speed * 60.0 / 1000.0 if speed != 0xff else 0

        lp = LogPoint(
            timestamp=time,
            speed=speed,
            temperature=buf.be_int16_from(8),
            airpressure=buf.be_uint32_from(12) / 100.0,
        )

        hr = buf.uint8_from(4)
        if hr != 0xff:
            lp.heartrate = hr

        cad = buf.uint8_from(5)
        if cad != 0xff:
            lp.cadence = cad

        log_points.append(lp)

        buf.set_offset(22)

    return log_points



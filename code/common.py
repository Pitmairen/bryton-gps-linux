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

from __future__ import print_function

import sys
import struct


def print_msg(msg, *args):
    print(msg, *args, sep=' ', file=sys.stderr)


class AvgMax(object):

    __slots__ = ('avg', 'max')

    def __init__(self, avg, max):
        self.avg = avg
        self.max = max



class TrackPoint(object):

    __slots__ = ('timestamp', 'latitude', 'longitude', 'elevation')

    def __init__(self, timestamp, longitude, latitude, elevation):
        self.timestamp = timestamp
        self.longitude = longitude
        self.latitude = latitude
        self.elevation = elevation



class LogPoint(object):

    __slots__ = ('timestamp', 'temperature', 'speed', 'watts', 'cadence',
                 'heartrate', 'airpressure')

    def __init__(self, timestamp, speed, watts=None, cadence=None,
                 heartrate=None, temperature=None, airpressure=None):

        self.timestamp = timestamp
        self.speed = speed
        self.watts = watts
        self.cadence = cadence
        self.heartrate = heartrate
        self.temperature = temperature
        self.airpressure = airpressure



class DataBuffer(object):

    def __init__(self, device, data, rel_offset=0, abs_offset=0,
                 data_len=None):
        self.device = device
        self.data = data
        self.rel_offset = rel_offset
        self.abs_offset = abs_offset
        self.data_len = data_len or self.device.BLOCK_SIZE

    @property
    def abs_position(self):
        return self.abs_offset + self.rel_offset

    def buffer_from(self, offset):

        return DataBuffer(self.device, self.data, self.rel_offset + offset,
                          self.abs_offset, self.data_len)

    def set_offset(self, offset):
        self.rel_offset += offset

    def read_from(self, offset, length):

        start_offset = self.rel_offset + offset
        end_offset = start_offset + length - 1

        if end_offset >= self.data_len:

            blocks = end_offset / self.device.BLOCK_SIZE

            for b in range(blocks):

                abs_offset = self.abs_offset + end_offset + \
                    b * self.device.BLOCK_SIZE

                block_addr = self.device.offset_to_block(abs_offset)
                self.data.extend(self.device.read_block(block_addr))
                self.data_len += self.device.BLOCK_SIZE

        return self.data[start_offset:start_offset + length]


    def int32_from(self, offset):
        return struct.unpack('i', self.read_from(offset, 4))[0]

    def uint32_from(self, offset):
        return struct.unpack('I', self.read_from(offset, 4))[0]

    def int16_from(self, offset):
        return struct.unpack('h', self.read_from(offset, 2))[0]

    def uint16_from(self, offset):
        return struct.unpack('H', self.read_from(offset, 2))[0]

    def int8_from(self, offset):
        return struct.unpack('b', self.read_from(offset, 1))[0]

    def uint8_from(self, offset):
        return struct.unpack('B', self.read_from(offset, 1))[0]

    def str_from(self, offset, length):
        return self.read_from(offset, length).tostring()

    # Big-endian:

    def be_int32_from(self, offset):
        return struct.unpack('>i', self.read_from(offset, 4))[0]

    def be_uint32_from(self, offset):
        return struct.unpack('>I', self.read_from(offset, 4))[0]

    def be_int16_from(self, offset):
        return struct.unpack('>h', self.read_from(offset, 2))[0]

    def be_uint16_from(self, offset):
        return struct.unpack('>H', self.read_from(offset, 2))[0]



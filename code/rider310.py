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

import re
import os
import time
import datetime

import rider40
import rider20p
import fitparse

from utils import cached_property
from common import AvgMax, TrackPoint, LogPoint



class FSReader(rider20p.FSReader):
    pass


class Rider310(rider20p.Rider20p):

    has_altimeter = True


    def read_serial(self):

        with open(self.fs.abs_path('System/device.txt')) as f:
            content = f.read()
            m = re.search(r'UUID=(\d+)', content)
            if m:
                return m.group(1)

    def get_history_files(self):
        return filter(lambda x: x.endswith('.sum'),
                   self.fs.listdir('System/History/Summary'))

    def open_fit_file(self, filename):
        return fitparse.FitFile(self.fs.abs_path(filename),
            data_processor=fitparse.StandardUnitsDataProcessor(),
        )

    def open_trackpoint_file(self, id):
        return self.open_fit_file('{0}.fit'.format(id))

    def open_logpoint_file(self, id):
        return self.open_fit_file('{0}.fit'.format(id))

    def open_summary_file(self, id):
        return self.open_fit_file('System/History/Summary/{0}.sum'.format(id))



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
    def storage_usage(self):
        st = os.stat(self.device.fs.abs_path('{0}.fit'.format(self._id)))
        # Just divide it by two, even though it is probably not correct
        return dict(trackpoints=st.st_size/2.0, logpoints=st.st_size/2.0)


    @cached_property
    def _read_summaries(self):

        buf = self.device.open_summary_file(self._id)

        laps = []

        if self.lap_count > 0:
            laps = _read_laps(buf)

        return _read_session_summary(buf), laps



def _read_trackpoint_segments(fit_file):

    segments = []

    segments.append(_read_trackpoint_segment(fit_file))

    return segments


def _read_trackpoint_segment(fit_file):

    messages = fit_file.get_messages(
        name="record",
    )
    s = rider40.TrackPointSegment()

    s.segment_type = 1 # Just set it to something

    for message in messages:
        if message.get_value('position_lat') is None:
            continue

        s.append(_read_trackpoint(message))

    if len(s) > 0:
        s.timestamp = s[0].timestamp

    return s



def _read_trackpoint(message):

    return TrackPoint(
        timestamp=_get_timestamp(message.get_value('timestamp')),
        longitude=message.get_value('position_long'),
        latitude=message.get_value('position_lat'),
        elevation=message.get_value('altitude')
    )



def _read_logpoint_segments(fit_file):
    segments = []
    segments.append(_read_logpoint_segment(fit_file))
    return segments


def _read_logpoint_segment(fit_file):

    messages = fit_file.get_messages(
        name="record",
    )
    s = rider40.LogPointSegment()

    s.segment_type = 2 # Just set it to something

    for message in messages:
        if message.get_value('speed') is None:
            continue

        s.append(_read_logpoint(message))

    if len(s) > 0:
        s.timestamp = s[0].timestamp

    return s



def _read_logpoint(message):

    return LogPoint(
        timestamp=_get_timestamp(message.get_value('timestamp')),
        temperature=message.get_value('temperature'),
        speed=message.get_value('speed'),
        watts=message.get_value('power'),
        cadence=message.get_value('cadence'),
        heartrate=message.get_value('heart_rate'),
    )



def _read_laps(fit_file):

    messages = fit_file.get_messages(
        name="lap",
    )

    laps = []

    for message in messages:

        laps.append(_read_summary(message))

    return laps


def _read_session_summary(fit_file):

    messages = fit_file.get_messages(
        name="session",
    )
    for message in messages:
        return _read_summary(message)


def _read_summary(message):

    s = rider40.Summary()

    s.start = _get_timestamp(message.get_value('start_time'))
    s.end = _get_timestamp(message.get_value('start_time')\
        + datetime.timedelta(seconds=message.get_value('total_elapsed_time')))
    s.distance = message.get_value('total_distance')


    if message.get_value('avg_speed') is not None:
        s.speed = AvgMax(
            message.get_value('avg_speed') * 3.6,
            message.get_value('max_speed') * 3.6,
        )

    if message.get_value('avg_heart_rate') is not None:
        s.heartrate = AvgMax(
            message.get_value('avg_heart_rate'),
            message.get_value('max_heart_rate'),
        )

    if message.get_value('avg_cadence') is not None:
        s.cadence = AvgMax(
            message.get_value('avg_cadence'),
            message.get_value('max_cadence'),
        )


    if message.get_value('avg_power') is not None:
        s.watts = AvgMax(
            message.get_value('avg_power'),
            message.get_value('max_power'),
        )

    s.altitude_gain = message.get_value('total_ascent')
    s.altitude_loss = message.get_value('total_descent')
    s.calories = message.get_value('total_calories')
    s.ride_time = message.get_value('total_moving_time')

    return s


def read_history(device):

    files = device.get_history_files()
    files.sort()

    history = []

    for f in files:

        fitfile = fitparse.FitFile(device.fs.abs_path(f),
            data_processor=fitparse.StandardUnitsDataProcessor(),
        )
        messages = fitfile.get_messages(
            name="session",
        )

        for n, message in enumerate(messages, 1):

            _id = os.path.basename(f).split('.')[0]
            timestamp = message.get_value('start_time')

            t = Track(device, _id)
            t.name = str(timestamp)
            t.timestamp = _get_timestamp(timestamp)
            t.lap_count = message.get_value('num_laps')

            history.append(t)

            break

    return history


def _get_timestamp(dt):
    return time.mktime(dt.utctimetuple())

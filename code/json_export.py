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

import json

from collections import OrderedDict

from gpx import format_timestamp




def _create_summary(sum):

    d = OrderedDict((
        ('start', format_timestamp(sum.start)),
        ('end', format_timestamp(sum.end)),
        ('distance', sum.distance),
        ('calories', sum.calories),
        ('ride_time', sum.ride_time),
        ('altitude_gain', sum.altitude_gain),
        ('altitude_loss', sum.altitude_loss),
    ))

    if sum.speed is not None:
        d['speed'] = OrderedDict((('avg', sum.speed.avg),
                                  ('max', sum.speed.max)))
    if sum.heartrate is not None and sum.heartrate.max > 0:
        d['heartrate'] = OrderedDict((('avg', sum.heartrate.avg),
                                      ('max', sum.heartrate.max)))
    if sum.cadence is not None and sum.cadence.max > 0:
        d['cadence'] = OrderedDict((('avg', sum.cadence.avg),
                                    ('max', sum.cadence.max)))
    if sum.watts is not None and sum.watts.max > 0:
        d['watts'] = OrderedDict((('avg', sum.watts.avg),
                                  ('max', sum.watts.max)))

    return d


def track_to_json(track, pretty=False):

    out = OrderedDict()

    out['name'] = track.name
    out['timestamp'] = format_timestamp(track.timestamp)

    trackpoints = []
    for seg in track.trackpoints:
        segment = []
        for tp in seg:
            segment.append(OrderedDict((
                ('timestamp', format_timestamp(tp.timestamp)),
                ('latitude', tp.latitude),
                ('longitude', tp.longitude),
                ('elevation', tp.elevation),
            )))
        trackpoints.append(segment)
    out['trackpoints'] = trackpoints


    logpoints = []
    for seg in track.logpoints:
        segment = []
        for lp in seg:
            d = OrderedDict((
                ('timestamp', format_timestamp(lp.timestamp)),
            ))
            if lp.speed is not None:
                d['speed'] = lp.speed
            if lp.temperature is not None:
                d['temperature'] = lp.temperature
            if lp.airpressure is not None:
                d['airpressure'] = lp.airpressure
            if lp.cadence is not None:
                d['cadence'] = lp.cadence
            if lp.heartrate is not None:
                d['heartrate'] = lp.heartrate
            if lp.watts is not None:
                d['watts'] = lp.watts

            segment.append(d)

        logpoints.append(segment)
    out['logpoints'] = logpoints


    laps = []
    if track.lap_count > 0:
        for sum in track.lap_summaries:
            laps.append(_create_summary(sum))
    out['laps'] = laps

    out['summary'] = _create_summary(track.summary)



    if pretty:
        return json.dumps(out, indent=1, separators=(',', ': '))

    return json.dumps(out)



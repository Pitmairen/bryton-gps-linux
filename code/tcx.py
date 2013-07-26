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

from xml.etree import cElementTree as xml


from utils import indent_element_tree
from gpx import format_timestamp, _ns, xsi_ns

_TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_TCX_NS_XSD = "http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
_ACT_EXT_NS = 'http://www.garmin.com/xmlschemas/ActivityExtension/v2'
_ACT_EXT_NS_XSD = 'http://www.garmin.com/xmlschemas/ActivityExtensionv2.xsd'


def tcx_ns(name):
    return _ns(name, _TCX_NS)


def aext_ns(name):
    return _ns(name, _ACT_EXT_NS)


def kph_to_ms(value):

    return value * 1000 / 3600


def create_sub_value(parent, name, text, ns=tcx_ns):

    el = xml.SubElement(parent, name)
    xml.SubElement(el, ns('Value')).text = text


def create_lap(sum, parent, ns=tcx_ns):

    lap = xml.SubElement(parent, ns('Lap'))

    lap.set(ns('StartTime'), format_timestamp(sum.start))

    xml.SubElement(lap, ns('TotalTimeSeconds')).text = \
        format(sum.end - sum.start, '.1f')
    xml.SubElement(lap, ns('DistanceMeters')).text = \
        format(sum.distance, '.1f')
    xml.SubElement(lap, ns('MaximumSpeed')).text = \
        format(kph_to_ms(sum.speed.max), '.2f')
    xml.SubElement(lap, ns('Calories')).text = \
        format(sum.calories, 'd')

    if sum.heartrate is not None and sum.heartrate.max > 0:

        create_sub_value(lap, ns('AverageHeartRateBpm'),
                         format(sum.heartrate.avg, 'd'))
        create_sub_value(lap, ns('MaximumHeartRateBpm'),
                         format(sum.heartrate.max, 'd'))

    xml.SubElement(lap, ns('Intensity')).text = 'Active'

    if sum.cadence is not None and sum.cadence.max > 0:
        xml.SubElement(lap, ns('Cadence')).text = format(sum.cadence.avg, 'd')

    xml.SubElement(lap, ns('TriggerMethod')).text = 'Manual'

    return lap


def create_track(seg, parent, ns=tcx_ns):

    track = xml.SubElement(parent, ns('Track'))

    for tp, lp in seg:
        create_trackpoint(tp, lp, track, ns)


def create_trackpoint(tp, lp, parent, ns=tcx_ns):

    p = xml.SubElement(parent, ns('Trackpoint'))

    xml.SubElement(p, ns('Time')).text = \
        format_timestamp(tp and tp.timestamp or lp.timestamp)

    if tp:
        create_position(tp, p, ns)
        xml.SubElement(p, ns('AltitudeMeters')).text = format(tp.elevation, '.1f')

    if lp and lp.heartrate is not None:
        create_sub_value(p, ns('HeartRateBpm'), format(lp.heartrate, 'd'))
    if lp and lp.cadence is not None:
        xml.SubElement(p, ns('Cadence')).text = format(lp.cadence, 'd')
    if lp and lp.speed > 0:
        create_tpx(lp, p)


def create_tpx(lp, parent, ns=aext_ns):

    tpx = create_ext(parent, ns('TPX'))

    xml.SubElement(tpx, ns('Speed')).text = format(kph_to_ms(lp.speed), '.2f')

    if lp.watts is not None:
        xml.SubElement(tpx, ns('Watts')).text = format(lp.watts, 'd')



def create_ext(parent, name, ns=tcx_ns):

    el = xml.SubElement(parent, ns('Extensions'))
    return xml.SubElement(el, name)


def create_position(tp, parent, ns=tcx_ns):

    pos = xml.SubElement(parent, ns('Position'))

    xml.SubElement(pos, ns('LatitudeDegrees')).text = format(tp.latitude,
                                                             '.6f')
    xml.SubElement(pos, ns('LongitudeDegrees')).text = format(tp.longitude,
                                                              '.6f')


def create_lap_ext(sum, parent, ns=aext_ns):

    lx = create_ext(parent, ns('LX'))

    xml.SubElement(lx, ns('AvgSpeed')).text = \
        format(kph_to_ms(sum.speed.avg), '.2f')

    if sum.cadence is not None and sum.cadence.max > 0:
        xml.SubElement(lx, ns('MaxBikeCadence')).text = \
            format(sum.cadence.max, 'd')

    if sum.watts is not None and sum.watts.max > 0:

        xml.SubElement(lx, ns('AvgWatts')).text = format(sum.watts.avg, 'd')
        xml.SubElement(lx, ns('MaxWatts')).text = format(sum.watts.max, 'd')


def create_laps(track, no_laps, parent, ns=tcx_ns):

    for sum, segments in _get_lap_trackpoints(track, no_laps):

        lap = create_lap(sum, parent, ns)

        for seg in segments:
            if seg:
                create_track(seg, lap, ns)

        create_lap_ext(sum, lap)



def create_fake_creator_element(parent, ns=tcx_ns):
    """Add fake creator to make strava.com trust the elevation data"""

    creator = xml.SubElement(parent, ns('Creator'))
    creator.set(xsi_ns('type'), 'Device_t')

    xml.SubElement(creator, ns('Name')).text = 'Garmin Edge 800'
    xml.SubElement(creator, ns('UnitId')).text = '9999999'
    xml.SubElement(creator, ns('ProductID')).text = '1169'

    version = xml.SubElement(creator, ns('Version'))
    xml.SubElement(version, ns('VersionMajor')).text = '0'
    xml.SubElement(version, ns('VersionMinor')).text = '0'
    xml.SubElement(version, ns('BuildMajor')).text = '0'
    xml.SubElement(version, ns('BuildMinor')).text = '0'



def create_author_element(parent, ns=tcx_ns):

    author = xml.SubElement(parent, ns('Author'))
    author.set(xsi_ns('type'), 'Application_t')

    xml.SubElement(author, ns('Name')).text = 'Bryton GPS Linux'

    build = xml.SubElement(author, ns('Build'))
    version = xml.SubElement(build, ns('Version'))
    xml.SubElement(version, ns('VersionMajor')).text = '0'
    xml.SubElement(version, ns('VersionMinor')).text = '1'
    xml.SubElement(version, ns('BuildMajor')).text = '0'
    xml.SubElement(version, ns('BuildMinor')).text = '0'

    xml.SubElement(author, ns('LangID')).text = 'en'
    xml.SubElement(author, ns('PartNumber')).text = '000-D123-00'



def track_to_tcx(track, pretty=False, fake_garmin_device=False, no_laps=False):

    ns = tcx_ns

    root = xml.Element(ns('TrainingCenterDatabase'))

    root.set(xsi_ns('schemaLocation'), ' '.join([
        _TCX_NS, _TCX_NS_XSD, _ACT_EXT_NS, _ACT_EXT_NS_XSD]))


    xml.register_namespace('', _TCX_NS)
    xml.register_namespace('_ns3', _ACT_EXT_NS)

    activities = xml.SubElement(root, ns('Activities'))
    activity = xml.SubElement(activities, ns('Activity'))
    activity.set(ns('Sport'), 'Biking')

    xml.SubElement(activity, ns('Id')).text = \
        format_timestamp(track.timestamp)


    create_laps(track, no_laps, activity, ns)

    if fake_garmin_device:
        create_fake_creator_element(activity, ns)


    create_author_element(root, ns)

    if pretty:
        indent_element_tree(root, ws=' ')

    out = xml.tostring(root)

    # ElementTree doesn't let me set prefix ns3 and a lot of software
    # seems to be hardcoded to use ns3 so have to use this little hack.
    out = out.replace('_ns3:', 'ns3:').replace('xmlns:_ns3', 'xmlns:ns3')

    return "<?xml version='1.0' encoding='utf-8'?>\n" + out


def _get_lap_trackpoints(track, no_laps):

    if no_laps:
        summaries = [track.summary]
    else:
        summaries = track.lap_summaries[:]

    lap = (summaries.pop(0), [[]])
    laps = [lap]
    first = True

    for seg in track.merged_segments(remove_empty_track_segs=False):

        if first:
            # Sometimes the first segment is a small segment without
            # trackpoints. We just remove this, Bryton's own software
            # seems to be doing the same.
            first = False
            seg = list(seg)
            if len(seg) < 5:
                # If it contains no trackpoints we remove it.
                if not [1 for tp, lp in seg if tp is not None]:
                    continue

        for tp, lp in seg:

            timestamp = tp.timestamp if tp is not None else lp.timestamp

            if timestamp < lap[0].end or not summaries:
                lap[1][-1].append((tp, lp))
            else:
                lap = (summaries.pop(0), [[(tp, lp)]])
                laps.append(lap)

        lap[1].append([])

    return laps


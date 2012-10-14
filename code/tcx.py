
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



def track_to_tcx(track, pretty=False):

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

    lap = create_lap(track.summary, activity, ns)

    for seg in track.merged_segments():

        create_track(seg, lap, ns)
    create_lap_ext(track.summary, lap)


    if pretty:
        indent_element_tree(root, ws=' ')

    out = xml.tostring(root)

    # ElementTree doesn't let me set prefix ns3 and a lot of software
    # seems to be hardcoded to use ns3 so have to use this little hack.
    out = out.replace('_ns3:', 'ns3:').replace('xmlns:_ns3', 'xmlns:ns3')

    return "<?xml version='1.0' encoding='utf-8'?>\n" + out





import datetime

from xml.etree import cElementTree as xml

from utils import indent_element_tree


_GPX_NS = "http://www.topografix.com/GPX/1/1"
_GPX_NS_XSD = "http://www.topografix.com/GPX/1/1/gpx.xsd"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_GPXX_NS = "http://www.garmin.com/xmlschemas/GpxExtensions/v3"
_GPXX_NS_XDS = "http://www.garmin.com/xmlschemas/GpxExtensionsv3.xds"
_TPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
_TPX_NS_XDS = "http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xds"


_from_ts = datetime.datetime.fromtimestamp


def _ns(name, ns):
    return '{{{}}}{}'.format(ns, name)


def gpx_ns(name):
    return _ns(name, _GPX_NS)


def xsi_ns(name):
    return _ns(name, _XSI_NS)


def gpxx_ns(name):
    return _ns(name, _GPXX_NS)


def tpx_ns(name):
    return _ns(name, _TPX_NS)


def format_timestamp(ts):
    return _from_ts(ts).strftime('%Y-%m-%dT%H:%M:%SZ')


def create_trkpt(trkpt, parent, ns=gpx_ns):

    p = xml.SubElement(parent, ns('trkpt'))

    p.set(ns('lat'), format(trkpt.latitude, '.6f'))
    p.set(ns('lon'), format(trkpt.longitude, '.6f'))

    xml.SubElement(p, ns('ele')).text = format(trkpt.elevation, '.1f')
    xml.SubElement(p, ns('time')).text = format_timestamp(trkpt.timestamp)

    return p


def create_trkseg(seg, parent, ns=gpx_ns):

    trkseg = xml.SubElement(parent, ns('trkseg'))

    for tp in seg:
        create_trkpt(tp, trkseg, ns)

    return trkseg


def create_tpx_trkseg(seg, parent, ns=gpx_ns):

    trkseg = xml.SubElement(parent, ns('trkseg'))

    for tp, lp in seg:

        if not tp:
            continue

        trkpt = create_trkpt(tp, trkseg, ns)

        if lp and has_values_for_tpx(lp):

            ext = xml.SubElement(trkpt, ns('extensions'))

            create_tpx(lp, ext)


    return trkseg


def has_values_for_tpx(lp):

    return lp.heartrate is not None or lp.temperature is not None or \
        lp.cadence is not None


def create_tpx(tp, parent, ns=tpx_ns):

    tpx = xml.SubElement(parent, ns('TrackPointExtension'))

    if tp.temperature is not None:
        xml.SubElement(tpx, ns('atemp')).text = format(tp.temperature, '.1f')

    if tp.heartrate is not None:
        xml.SubElement(tpx, ns('hr')).text = format(tp.heartrate, 'd')

    if tp.cadence is not None:
        xml.SubElement(tpx, ns('cad')).text = format(tp.cadence, 'd')


def track_to_plain_gpx(track, pretty=False):

    ns = gpx_ns

    root = xml.Element(ns('gpx'))

    root.set(xsi_ns('schemaLocation'), ' '.join([_GPX_NS, _GPX_NS_XSD]))

    root.set(ns('version'), '1.1')
    root.set(ns('creator'), 'Bryton-GPS-Linux')

    xml.register_namespace('', _GPX_NS)

    trk = xml.SubElement(root, ns('trk'))

    for seg in track.trackpoints:

        if seg:
            create_trkseg(seg, trk, ns)


    if pretty:
        indent_element_tree(root, ws=' ')

    return "<?xml version='1.0' encoding='utf-8'?>\n" + xml.tostring(root)


def track_to_garmin_gpxx(track, pretty=False):

    ns = gpx_ns

    root = xml.Element(ns('gpx'))

    root.set(xsi_ns('schemaLocation'), ' '.join([
        _GPX_NS, _GPX_NS_XSD, _TPX_NS, _TPX_NS_XDS]))

    root.set(ns('version'), '1.1')
    root.set(ns('creator'), 'Bryton-GPS-Linux')

    xml.register_namespace('', _GPX_NS)
    xml.register_namespace('gpxtpx', _TPX_NS)

    trk = xml.SubElement(root, ns('trk'))

    for seg in track.merged_segments():

        create_tpx_trkseg(seg, trk, ns)


    if pretty:
        indent_element_tree(root, ws=' ')

    return "<?xml version='1.0' encoding='utf-8'?>\n" + xml.tostring(root)






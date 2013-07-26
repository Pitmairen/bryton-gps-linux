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

import sys
import glob
import contextlib
import argparse
import warnings
import datetime
import os
import getpass
import time

from functools import partial

import rider40
import common
import gpx
import tcx
import strava



def find_device():

    devices = glob.glob('/dev/disk/by-id/usb-BRYTON_MASS_STORAGE_*')
    if len(devices) > 1:
        raise RuntimeError('Multiple Devices Found')
    elif not devices:
        raise RuntimeError('Device Not Found')

    device = devices[0]

    return device


def get_device(dev):


    data = dev.read_addr(6, 1, 0x10).tostring()

    if not data.startswith('Hera Data'):
        return None


    dev_id = data[16:16 + 4]

    if dev_id not in ['1504', '1510']:
        warnings.warn('Unknown device model.', RuntimeWarning)

    return rider40, rider40.Rider40(dev)


def open_device(dev_path):
    dev_access = common.DeviceAccess(dev_path)
    dev_access.open()
    return contextlib.closing(dev_access)



def get_tracks(history, track_ids):
    tracks = []
    for id in track_ids:
        try:
            tracks.append(history[int(id)])
        except (IndexError, TypeError):
            raise RuntimeError('Invalid track_id {0}'.format(id))
    return tracks


def print_history(history, print_storage=False):

    if not history:
        print "No tracks"
        return

    i = 0
    for t in history:
        if print_storage:
            u = t.storage_usage
            print format(i, '2d'), ':', t.name, ' - Trackpoints ', \
                    format_bytes(u['trackpoints']), ' - ', \
                    'Logpoints', format_bytes(u['logpoints'])
        else:
            print format(i, '2d'), ':', t.name
        i += 1


def print_summaries(tracks, print_storage=False):

    for t in tracks:

        print_summary(t.summary, t, print_storage)


def print_summary(s, track=None, print_storage=False):

    ts = datetime.datetime.fromtimestamp

    print '==================================================='
    print ts(s.start)
    print '{0} - {1} ({2})'.format(ts(s.start), ts(s.end),
                                   datetime.timedelta(seconds=s.ride_time))

    print '   Dist: {0:.2f}Km'.format(s.distance / 1000.0)
    print '    Cal: {0}'.format(s.calories)
    print '    Alt: {0}m / {1}m (gain/loss)'.format(s.altitude_gain,
                                                  s.altitude_loss)
    print '  Speed: {0}Kph / {1}Kph (avg/max)'.format(s.speed.avg, s.speed.max)

    if s.heartrate is not None and s.heartrate.max > 0:
        print '     Hr: {0}bpm / {1}bpm (avg/max)'.format(s.heartrate.avg,
                                                        s.heartrate.max)
    if s.cadence is not None and s.cadence.max > 0:
        print '    Cad: {0}rpm / {1}rpm (avg/max)'.format(s.cadence.avg,
                                                        s.cadence.max)
    if s.watts is not None and s.watts.max > 0:
        print '  Watts: {0}/{1} (avg/max)'.format(s.watts.avg,
                                                s.watts.max)

    if track is not None and track.lap_count > 0:
        print '   Laps: {0}'.format(len(track.lap_summaries))

    if print_storage:
        u = track.storage_usage
        print 'Storage: Trackpoints', \
                    format_bytes(u['trackpoints']), ' - ', \
                    'Logpoints', format_bytes(u['logpoints'])


def print_storage_usage(device):

    print '{:>12} | {:>10} | {:>16} | {:>10}'.format('Type', 'Total', 'Used', 'Left')
    print '{}|{}|{}|{}'.format('-'*13, '-'*12, '-'*18, '-'*17)

    u = device.read_storage_usage()

    _print_storage_row(u, 'trackpoints', 'Trackpoints')
    _print_storage_row(u, 'logpoints', 'Logpoints')
    _print_storage_row(u, 'tracklist', 'Tracks')
    _print_storage_row(u, 'laps', 'Laps')



def _print_storage_row(u, key, title):
    print '{:>12} | {:>10} | {:>10} ({:>2}%) | {:>10} ({:>2}%)'.format(
    title,
    format_bytes(u[key]['total']),
    format_bytes(u[key]['total'] - u[key]['left']),
    100 * (u[key]['total'] - u[key]['left']) / u[key]['total'],
    format_bytes(u[key]['left']),
    100 - 100 * (u[key]['total'] - u[key]['left']) / u[key]['total'])




def export_tracks(tracks, export_func, file_ext, args):

    if args.out_name is not None and len(tracks) > 1:
        raise RuntimeError('--out-name can only be used with a single track.')

    for t in tracks:

        out = export_func(t, pretty=args.no_whitespace)

        if args.save_to is None and args.out_name is None:
            print out
            continue

        if args.out_name:
            path = args.out_name
        else:
            fname = t.name.replace('/', '').replace(':', '') \
                .replace(' ', '-') + '.' + file_ext
            path = os.path.join(args.save_to, fname)


        with open(path, 'w') as f:

            f.write(out)


def export_fake_garmin(tracks, args):

    export_func = partial(tcx.track_to_tcx, fake_garmin_device=True)

    export_tracks(tracks, export_func, 'tcx', args)



def upload_strava(tracks, args, fake_garmin_device=False):

    if args.strava_email is None:
        print 'Missing email for strava.com'
        return

    password = args.strava_password
    if password is None:
        password = getpass.getpass('Strava.com password:')


    uploader = strava.StravaUploader(fake_garmin_device=fake_garmin_device)

    try:
        print 'Authenticating to strava.com'
        uploader.authenticate(args.strava_email, password)
    except strava.StravaError, e:
        print 'StravaError:', e.reason
        return

    for t in tracks:

        try:
            print 'Uploading track: {0}'.format(t.name)
            upload = uploader.upload(t)

            while not upload.finished:
                time.sleep(3)
                p = upload.check_progress()

            print 'Uploaded OK'



        except strava.StravaError, e:
            print 'StravaError:', e.reason



def options():

    p = argparse.ArgumentParser(description='Bryton GPS Linux')

    p.add_argument('--device', '-D',
                   help='Path to the device. If not specified'
                        ' it will try to be autodetected.')

    p.add_argument('--list-history', '-L', action='store_true',
                   help='List track history')

    p.add_argument('--tracks', '-T', nargs='+',
                   help='Tracks ids to do actions upon. '
                        'Ids can be found using --list-history.')

    p.add_argument('--summary', action='store_true',
                   help='Print summary of the selected tracks.')
    p.add_argument('--gpx', action='store_true',
                   help='Generate plain GPX files of the selected tracks.')
    p.add_argument('--gpxx', action='store_true',
                   help='Generate GPX files using Garmin TrackPointExtension '
                        'of the selected tracks.')
    p.add_argument('--tcx', action='store_true',
                   help='Generate TCX files of the selected tracks.')
    p.add_argument('--save-to', '-S',
                   help='Directory to store expored files.')
    p.add_argument('--out-name', '-O',
                   help='Filename to export to. Only one track.')
    p.add_argument('--no-whitespace', action='store_false',
                   help='No unnecessary whitespace in exported files.')

    p.add_argument('--strava', action='store_true',
                   help='Upload tracks to strava.com')

    p.add_argument('--strava-email', nargs='?',
                   help='strava.com email')

    p.add_argument('--strava-password', nargs='?',
                   help='strava.com password')

    p.add_argument('--fake-garmin', action='store_true',
                   help='This will add a created with Garmin Edge 800 element '
                        'to tcx files which will make strava.com trust the '
                        'elevation data. Useful if your device has an '
                        'altimeter. Used when exporting to tcx and when '
                        'uploading to strava.com')
    p.add_argument('--fix-elevation', nargs='?', type=int, metavar='N',
                   help='Set the elevation of the first trackpoint to N. '
                        'The other trackpoints will be adjusted relative to '
                        'the first one. '
                        'This is useful if you forget to calibrate the '
                        'altimeter before the ride and you know the elevation '
                        'where you started. Only useful if you device has an '
                        'altimeter.')

    p.add_argument('--strip-elevation', action='store_true',
                   help='Set the elevation to 0 on all trackpoints.')

    p.add_argument('--use-elevation-db', action='store_true',
                   help='Use the SRTM Elevation Database v4.1 to set the '
                        'elevation. Requires the GDAL library.')

    p.add_argument('--storage', action='store_true',
                   help='This will show the storage usage on the deviced. '
                        'When used together with --list-history or --summary '
                        'the storage space used by each track will be shown.')
    return p


def main():

    opts = options()
    args = opts.parse_args()


    dev_path = args.device

    if dev_path is None:
        dev_path = find_device()


    with open_device(dev_path) as dev_access:

        module, device = get_device(dev_access)

        if args.list_history or args.tracks:
            history = list(reversed(module.read_history(device)))


        if args.list_history:
            print_history(history, args.storage)

        elif args.tracks:

            tracks = get_tracks(history, args.tracks)

            if args.summary:
                print_summaries(tracks, args.storage)
                return 0

            if args.fix_elevation:
                fix_elevation(tracks, args.fix_elevation)

            if args.strip_elevation:
                strip_elevation(tracks)

            if args.use_elevation_db:
                set_elevation_from_db(tracks)

            if args.gpx:
                export_tracks(tracks, gpx.track_to_plain_gpx, 'gpx', args)
            if args.gpxx:
                export_tracks(tracks, gpx.track_to_garmin_gpxx, 'gpx', args)
            if args.tcx:
                if args.fake_garmin:
                    export_fake_garmin(tracks, args)
                else:
                    export_tracks(tracks, tcx.track_to_tcx, 'tcx', args)
            if args.strava:
                upload_strava(tracks, args,
                              fake_garmin_device=args.fake_garmin)

        elif args.storage:
            print_storage_usage(device)
        else:
            opts.print_help()



    return 0


def strip_elevation(tracks):

    for t in tracks:
        for seg in t.trackpoints:
            for tp in seg:
                tp.elevation = 0


def set_elevation_from_db(tracks):

    import srtm

    db = srtm.SrtmLayer()

    for t in tracks:
        for seg in t.trackpoints:
            for tp in seg:
                tp.elevation = round(
                    db.get_elevation(tp.latitude, tp.longitude), 1)


def fix_elevation(tracks, new_elevation):
    for t in tracks:
        fix_track_elevation(t, new_elevation)


def fix_track_elevation(track, new_elevation):

    diff = None

    for seg in track.trackpoints:

        for tp in seg:

            if diff is None:
                diff = new_elevation - tp.elevation

            tp.elevation += diff

    return track


def format_bytes(num):
    for x in ['B','KB','MB','GB']:
        if num < 1024.0 and num > -1024.0:
            return "%3.1f%s" % (num, x)
        num /= 1024.0
    return "%3.1f%s" % (num, 'TB')


if __name__ == '__main__':

    try:
        sys.exit(main())
    except RuntimeError, e:
        print 'Error: ', e.message
        sys.exit(1)



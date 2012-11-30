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

    if dev_id != '1504':
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
            raise RuntimeError('Invalid track_id {}'.format(id))
    return tracks


def print_history(history):

    i = 0
    for t in history:
        print format(i, '2d'), ':', t.name
        i += 1



def print_summaries(tracks):

    for t in tracks:

        print_summary(t.summary)


def print_summary(s):

    ts = datetime.datetime.fromtimestamp

    print '==================================================='
    print ts(s.start)
    print '{} - {} ({})'.format(ts(s.start), ts(s.end),
                                datetime.timedelta(seconds=s.ride_time))

    print ' Dist: {:.2f}Km'.format(s.distance / 1000.0)
    print '  Cal: {}'.format(s.calories)
    print '  Alt: {}m / {}m (gain/loss)'.format(s.altitude_gain,
                                                s.altitude_loss)
    print 'Speed: {}Kph / {}Kph (avg/max)'.format(s.speed.avg, s.speed.max)

    if s.heartrate is not None and s.heartrate.max > 0:
        print '   Hr: {}bpm / {}bpm (avg/max)'.format(s.heartrate.avg,
                                                      s.heartrate.max)
    if s.cadence is not None and s.cadence.max > 0:
        print '  Cad: {}rpm / {}rpm (avg/max)'.format(s.cadence.avg,
                                                      s.cadence.max)
    if s.watts is not None and s.watts.max > 0:
        print 'Watts: {}/{} (avg/max)'.format(s.watts.avg,
                                              s.watts.max)



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



def upload_strava(tracks, args):

    if args.strava_email is None:
        print 'Missing email for strava.com'
        return

    password = args.strava_password
    if password is None:
        password = getpass.getpass('Strava.com password:')


    uploader = strava.StravaUploader()

    try:
        print 'Authenticating to strava.com'
        uploader.authenticate(args.strava_email, password)
    except strava.StravaError, e:
        print 'StravaError:', e.reason
        return

    for t in tracks:

        try:
            print 'Uploading track: {}'.format(t.name)
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
            print_history(history)

        elif args.tracks:

            tracks = get_tracks(history, args.tracks)

            if args.summary:
                print_summaries(tracks)
                return 0

            if args.gpx:
                export_tracks(tracks, gpx.track_to_plain_gpx, 'gpx', args)
            if args.gpxx:
                export_tracks(tracks, gpx.track_to_garmin_gpxx, 'gpx', args)
            if args.tcx:
                export_tracks(tracks, tcx.track_to_tcx, 'tcx', args)
            if args.strava:
                upload_strava(tracks, args)


        else:
            opts.print_help()



    return 0



if __name__ == '__main__':

    try:
        sys.exit(main())
    except RuntimeError, e:
        print 'Error: ', e.message
        sys.exit(1)



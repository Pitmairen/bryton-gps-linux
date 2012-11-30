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

import glob
import errno
import struct
import sys
import argparse

try:
    import py_sg
except ImportError, e:
    print('You need to install the "py_sg" module.')
    sys.exit(1)


def find_device():

    devices = glob.glob('/dev/disk/by-id/usb-BRYTON_MASS_STORAGE_*')
    if len(devices) > 1:
        raise RuntimeError('Multiple Devices Found')
    elif not devices:
        raise RuntimeError('Device Not Found')

    device = devices[0]

    return device



def open_device(path):
    try:
        return open(path, 'rb')
    except IOError as e:
        if e.errno == errno.EACCES:
            raise RuntimeError('Failed to open device "{}" '
                               '(Permission denied).'.format(path))

        raise


def pack_scsi_cmd(cmd):

    return struct.pack('{}B'.format(len(cmd)), *cmd)


def read_serial(dev):
    """
    SCSI Read(10) command with byte nr. 7 set to 0x03
    will return empty data with the the serial at the end.
    """

    cmd = [0x28, 0, 0, 0, 0, 0, 0x03, 0, 0, 0]

    s = struct.pack('>H', 4)

    cmd[7] = ord(s[0])
    cmd[8] = ord(s[1])


    return py_sg.read(dev, pack_scsi_cmd(cmd), 2048)[-16:]


def read_block(dev, addr):
    """
    SCSI Read(10) command with byte nr. 7 set to 0x10
    will return the data on the device in blocks of 4096 bytes.
    """

    cmd = [0x28, 0, 0, 0, 0, 0, 0x10, 0, 0, 0]

    blocks = 8

    a = struct.pack('>I', addr)
    cmd[2] = ord(a[0])
    cmd[3] = ord(a[1])
    cmd[4] = ord(a[2])
    cmd[5] = ord(a[3])

    s = struct.pack('>H', blocks)

    cmd[7] = ord(s[0])
    cmd[8] = ord(s[1])



    return py_sg.read(dev, pack_scsi_cmd(cmd), 512 * blocks)



def dump_device(dev, output):

    with open(output, 'wb') as f:

        for i in range(0x1ff):
            f.write(read_block(dev, i))





def main():

    parser = argparse.ArgumentParser(description='Dump Bryton GPS data')

    parser.add_argument('output')
    parser.add_argument('--device', '-D',
                        help='Path to the device. If not specified'
                             ' it will try to be autodetected.')


    args = parser.parse_args()

    dev = args.device

    try:
        if dev is None:
            dev = find_device()

        with open_device(dev) as dev:

            dump_device(dev, args.output)

    except RuntimeError, e:
        print ('Error:', e.message)
        return 1


    return 0

if __name__ == '__main__':

    sys.exit(main())

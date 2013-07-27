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

import struct
import array
import errno
import sys

from common import print_msg

try:
    import py_sg
except ImportError, e:
    print_msg('You need to install the "py_sg" module.')
    sys.exit(1)



def _scsi_pack_cdb(cmd):

    return struct.pack('{0}B'.format(len(cmd)), *cmd)



def _scsi_read10(addr, block_count, reserved_byte=0):

    cdb = [0x28, 0, 0, 0, 0, 0, reserved_byte, 0, 0, 0]


    a = struct.pack('>I', addr)
    cdb[2] = ord(a[0])
    cdb[3] = ord(a[1])
    cdb[4] = ord(a[2])
    cdb[5] = ord(a[3])

    s = struct.pack('>H', block_count)

    cdb[7] = ord(s[0])
    cdb[8] = ord(s[1])

    return _scsi_pack_cdb(cdb)



class DeviceAccess(object):

    BLOCK_SIZE = 512

    def __init__(self, dev_path):

        self.dev_path = dev_path
        self.dev = None


    def open(self):

        try:
            self.dev = open(self.dev_path, 'rb')
        except IOError as e:
            if e.errno == errno.EACCES:
                raise RuntimeError('Failed to open device "{0}" '
                                   '(Permission denied).'.format(
                                   self.dev_path))
            raise


    def close(self):
        self.dev.close()
        self.dev = None


    def read_addr(self, addr, block_count=8, read_type=0):


        cdb = _scsi_read10(addr, block_count, reserved_byte=read_type)

        data = py_sg.read(self.dev, cdb, self.BLOCK_SIZE * block_count)

        return array.array('B', data)



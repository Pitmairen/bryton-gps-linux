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
import urllib2

import cStringIO as StringIO

try:
    import mechanize
    has_mechanize = True
except ImportError:
    has_mechanize = False

import tcx


_URL_LOGIN = 'https://www.strava.com/login'
_URL_UPLOAD = 'http://app.strava.com/upload/select'
_URL_UPLOAD_STATUS = 'http://app.strava.com/upload/progress.json?' \
        'new_uploader=true&ids[]={id}'

StravaError = urllib2.URLError




def _open_url(browser, url):

    try:
        browser.open(url)
    except mechanize.HTTPError as e:
        raise StravaError(str(e))

def _get_response(browser):
    try:
        return json.loads(browser.response().get_data())
    except ValueError, e:
        raise StravaError('Failed to parse JSON response')


class StravaUploader(object):

    def __init__(self, fake_garmin_device=False):

        if not has_mechanize:
            raise RuntimeError('To upload to strava you need the ' \
                               '"mechanize" library (pip install mechanize)')

        self.token = None
        self.fake_garmin_device = fake_garmin_device

        self.browser = mechanize.Browser()


    def authenticate(self, email, password):

        _open_url(self.browser, _URL_LOGIN)

        try:
            self.browser.select_form(
                predicate=lambda f: 'id' in f.attrs and \
                f.attrs['id'] == 'login_form')
        except mechanize.FormNotFoundError as e:
            raise StravaError('Login form not found')


        self.browser['email'] = email
        self.browser['password'] = password

        try:
            self.browser.submit()
        except mechanize.HTTPError as e:
            raise StravaError(str(e))

        if self.browser.geturl() == _URL_LOGIN:
            raise StravaError('Failed to authenticate')


    def upload(self, track):

        _open_url(self.browser, _URL_UPLOAD)

        try:
            self.browser.select_form(
                predicate=lambda f: 'action' in f.attrs and \
                f.attrs['action'] == '/upload/files')
        except mechanize.FormNotFoundError as e:
            raise StravaError('Upload form not found')


        data = tcx.track_to_tcx(track, fake_garmin_device= \
                                      self.fake_garmin_device)

        self.browser.form.add_file(StringIO.StringIO(data),
                                   'text/plain',
                                   track.name + '.tcx')

        try:
            self.browser.submit()
        except mechanize.HTTPError as e:
            raise StravaError(str(e))

        resp = _get_response(self.browser)

        if len(resp) != 1:
            raise StravaError('Unexpected response')

        resp = resp[0]

        if 'error' in resp and resp['error'] is not None:
            raise StravaError(resp['error'])

        return UploadStatus(self.browser, resp['id'])






class UploadStatus(object):

    def __init__(self, browser, upload_id):
        self.browser = browser
        self.upload_id = upload_id

        self.finished = False
        self.status_msg = ''

    def check_progress(self):

        _open_url(self.browser, _URL_UPLOAD_STATUS.format(id=self.upload_id))


        resp = _get_response(self.browser)

        if len(resp) != 1:
            raise StravaError('Unexpected response')

        resp = resp[0]

        if 'error' in resp:
            raise StravaError(resp['error'])

        self.finished = int(resp['progress']) == 100
        self.status_msg = resp['workflow']

        return resp['progress']




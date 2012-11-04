
import urllib
import urllib2
import json


import tcx


_URL_AUTH = 'https://www.strava.com/api/v2/authentication/login'
_URL_UPLOAD = 'http://www.strava.com/api/v2/upload'
_URL_UPLOAD_STATUS = 'http://www.strava.com/api/v2/upload/status/{id}?' \
        'token={token}'

StravaError = urllib2.URLError



def urlencode(**kwargs):
    return urllib.urlencode(kwargs)


def _req(*args, **kwargs):

    req = urllib2.urlopen(*args, **kwargs)

    try:
        return json.loads(req.read())
    except ValueError, e:
        raise StravaError(e.message)



class StravaUploader(object):

    def __init__(self):
        self.token = None


    def authenticate(self, email, password):

        resp = _req(_URL_AUTH, urlencode(email=email,
                                         password=password))

        if 'error' in resp:
            raise StravaError(resp['error'])

        self.token = resp['token']


    def upload(self, track):

        data = json.dumps({
            'token' : self.token,
            'type' : 'tcx',
            'data' : tcx.track_to_tcx(track),
            'activity_type' : 'ride',
        })

        req = urllib2.Request(_URL_UPLOAD, data,
                               {'Content-Type' : 'application/json'})

        resp = _req(req)

        if 'error' in resp:
            raise StravaError(resp['error'])

        return UploadStatus(self.token, resp['upload_id'])




class UploadStatus(object):

    def __init__(self, token, upload_id):
        self.token = token
        self.upload_id = upload_id

        self.finished = False
        self.status_msg = ''

    def check_progress(self):

        resp = _req(_URL_UPLOAD_STATUS.format(id=self.upload_id,
                                              token=self.token))

        if 'upload_error' in resp:
            raise StravaError(resp['upload_error'])

        self.finished = int(resp['upload_progress']) == 100
        self.status_msg = resp['upload_status']

        return resp['upload_progress']




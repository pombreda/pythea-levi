from gaesessions import SessionMiddleware

# suggestion: generate your own random key using os.urandom(64)
# WARNING: Make sure you run os.urandom(64) OFFLINE and copy/paste the output to
# this file.  If you use os.urandom() to *dynamically* generate your key at
# runtime then any existing sessions will become junk every time you start,
# deploy, or update your app!
import os
COOKIE_KEY = 'T\xd4n\x08\xd2:\xca\xf9_\x90\xeb_\xc5\xa7\x90[\x1eTo\x1e\x14\x17\rPC}\xcf\xa7\x95\xe0\xe0\xaf*z\xb4\xd2\xa1Y\x97n_\xf0\xcd\xb3\x16\x93\xdd\xa7\x86\xfb\x8c+\x1eJ\xeem{\x8a\t\x1bZ\xc4\x1fB'

def webapp_add_wsgi_middleware(app):
  from google.appengine.ext.appstats import recording
  app = SessionMiddleware(app, cookie_key=COOKIE_KEY)
  app = recording.appstats_wsgi_middleware(app)
  return app

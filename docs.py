import sys
import os
import inspect

DIR_PATH = os.path.abspath(os.path.join('..', 'ae-python'))

EXTRA_PATHS = [
  DIR_PATH,
  os.path.join(DIR_PATH, 'lib', 'antlr3'),
  os.path.join(DIR_PATH, 'lib', 'django_0_96'),
  os.path.join(DIR_PATH, 'lib', 'fancy_urllib'),
  os.path.join(DIR_PATH, 'lib', 'ipaddr'),
  os.path.join(DIR_PATH, 'lib', 'protorpc'),
  os.path.join(DIR_PATH, 'lib', 'webob'),
  os.path.join(DIR_PATH, 'lib', 'webapp2'),
  os.path.join(DIR_PATH, 'lib', 'yaml', 'lib'),
  os.path.join(DIR_PATH, 'lib', 'simplejson'),
  os.path.join(DIR_PATH, 'lib', 'google.appengine._internal.graphy'),
]

sys.path = EXTRA_PATHS + sys.path

import main

application = main.application

for handler, patterns in application._pattern_map.items():
    for p in patterns:
        print p[0].pattern[1:-1]
        #print handler.get.im_class
        if main == inspect.getmodule(handler.post):
            print "HAS POST"

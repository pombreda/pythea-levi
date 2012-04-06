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
import forms
from django import forms as df

for item in inspect.getmembers(forms, inspect.isclass):
    print item[0], dir(item[1])
    print item[1].base_fields
    #print dir(item[1].Meta)
    if item[0] == 'DebtForm':
        print dir(item[1].base_fields['creditor'])
        print item[1].base_fields['creditor'].query
        print item[1].base_fields['creditor'].reference_class
        print dir(item[1].base_fields['creditor'].query)
        print item[1].base_fields['creditor'].query._get_query
        print item[1].base_fields['creditor'].query._model_class
        print item[1].base_fields['creditor'].query.filter
        print item[1].base_fields['creditor'].query.order

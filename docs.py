import sys
import os
import inspect
import re
import yaml

import simplejson as json

from collections import defaultdict
"""
DIR_PATH = os.path.abspath(os.path.join('..', 'ae-python'))

EXTRA_PATHS = [
  DIR_PATH,
  os.path.join(DIR_PATH, 'lib', 'antlr3'),
  os.path.join(DIR_PATH, 'lib', 'django_0_96'),
  os.path.join(DIR_PATH, 'lib', 'fancy_urllib'),
  os.path.join(DIR_PATH, 'lib', 'ipaddr'),
  os.path.join(DIR_PATH, 'lib', 'protorpc'),
  os.path.join(DIR_PATH, 'lib', 'webob_0_9'),
  os.path.join(DIR_PATH, 'lib', 'webapp2'),
  os.path.join(DIR_PATH, 'lib', 'yaml', 'lib'),
  os.path.join(DIR_PATH, 'lib', 'simplejson'),
  os.path.join(DIR_PATH, 'lib', 'google.appengine._internal.graphy'),
]

sys.path = EXTRA_PATHS + sys.path

"""

urlparms=re.compile(r'\(.*?\)')
reqparms=re.compile(r'self.request.(?:.*?.)?get\(\'(.*?)\'\)')
reqparms_multiple=re.compile(r'self.request.(?:.*?.)?get_all\(\'(.*?)\'\)')
forms=re.compile(r'forms\.(\w+)\(')

def get_args(args):
    args2 = args.args[1:]
    if args.defaults:
        for index, default in enumerate(args.defaults):
            args2[-index-1] = args2[-index-1] + '=' + str(default)
    return args2

def get_parms(source):
    return reqparms.findall(source)

def document(method, paths):
    args = inspect.getargspec(method)
    data = {}
    data['method'] = method.__name__.upper()
    data['path'] = re.sub(urlparms, replace(get_args(args)), paths)
    data['args'] = reqparms.findall(inspect.getsource(method))
    data['args'].extend([ s+'*' for s in reqparms_multiple.findall(inspect.getsource(method))])
    data['forms'] = forms.findall(inspect.getsource(method))
    data['doc'] = method.__doc__
    return data


class replace():
    def __init__(self, names):
        self.names = names
        self.index = 0

    def __call__(self, match):
        try:
            index = self.index
            self.index += 1
            return '<' + self.names[index] + '>'
        except IndexError:
            return '<unknown>'

class Document():
    def __init__(self, application, caller):
        self.module = inspect.getmodule(caller)
        routes = defaultdict(list)
        for handler, patterns in application._pattern_map.items():
            for p in patterns:
                template = p[0].pattern[1:-1]
                routes[handler].append(template)
        self.routes = routes

        docs = []
	for handler, paths in routes.items():
	    this = {}
	    this['class'] = handler.__name__
	    this['paths'] = paths
	    this['doc'] = handler.__doc__

	    parms = []
	    max = 0
	    longest = 0
	    for path in paths:
		parms.append(urlparms.findall(path))
		if len(parms[-1]) > max:
		   max = len(parms[-1])
		   longest = len(parms) - 1

	    methods = []
	    for method in ['post', 'get']:
		m = getattr(handler, method)
		if self.module == inspect.getmodule(m): # otherwise it is inherited
		    methods.append(document(m, paths[longest]))
	    this['methods'] = methods
	    docs.append(this)
            self.docs = docs


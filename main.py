from __future__ import with_statement
from google.appengine.dist import use_library
use_library('django', '1.2')
import os
import logging
import cgi
import datetime
import urllib
import wsgiref.handlers
import csv
import pickle

import re

from google.appengine.ext import db
from google.appengine.ext.db import polymodel
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from gaesessions import get_current_session

from StringIO import StringIO
from django.utils import simplejson
from django import forms
#import webapp2 as webapp

class User(polymodel.PolyModel):
    userid = db.StringProperty()
    email = db.EmailProperty()
    display_name = db.TextProperty()
    password = db.StringProperty()
    
    def authenticate(self, password):
        pass

class Organisation(polymodel.PolyModel):
    display_name = db.TextProperty()
    icon = db.LinkProperty()
    # Get it from website with either favicon.ico or from the homepage's head:
    # <link rel="shortcut icon" href="(.*?)" type=".*?" /?>
    website = db.LinkProperty()
    email = db.EmailProperty()

class SocialWorker(User):
    organisation = db.ReferenceProperty(Organisation)

class Client(User):
    firstname = db.StringProperty()
    lastname = db.StringProperty()
    address = db.PostalAddressProperty()
    phone = db.PhoneNumberProperty()
    mobile = db.PhoneNumberProperty()

class Creditor(Organisation):
    pass

class Debt(db.Model):
    creditor = db.ReferenceProperty(Creditor)
    amount = db.IntegerProperty() # Fixme: should create a Decimal property for this


categories = { 
    'Wonen, electriciteit, gas, ...': [
        'Electriciteit en gas',
        'Huurschulden',
        'Hypotheekschulden',
        'Water'],
    'Gezondheid': [
        'Dokterskosten',
        'Ziekenhuiskosten',
        'Verzekeringen'],
    'GSM, telefoon, internet, TV': [
        'GSM',
        'Telefoon',
        'Internet',
        'TV'],
    'Leningen': [
        'Consumentenkrediet',
        'Credit card',
        'Autolening',
        'Verkoop op afbetaling'],
    'Overheid': [
        'Boetes',
        'Belastingen',
        'Toeslagen',
        'Kinderopvang'],
}

class Main(webapp.RequestHandler):
    def get(self):
        session = get_current_session()
        user = session.get('user')
        if not user:
            self.redirect('/register')
            return

        vars = { 'categories': categories }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'main.html')
        self.response.out.write(template.render(path, vars))

class Register(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'register.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        # Read form variables and put the new user in the database
        pass

class Reset(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
        self.response.out.write(template.render(path, vars))

class EnterDebts(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'main.html')
        self.response.out.write(template.render(path, vars))

class Upload(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'upload.html')
        self.response.out.write(template.render(path, vars))

class Authorize(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'upload.html')
        self.response.out.write(template.render(path, vars))

class Creditors(webapp.RequestHandler):
    def get(self, category):
        
        path = os.path.join(os.path.dirname(__file__), 'templates', 'crediteuren.html')
        self.response.out.write(template.render(path, vars))

class ShowDebts(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'upload.html')
        self.response.out.write(template.render(path, vars))

application = webapp.WSGIApplication([
  (r'/', Main),
  (r'/register', Register),
  (r'/enter', EnterDebts),
  (r'/upload', Upload),
  (r'/authorize', Authorize),
  (r'/crediteuren/(.*)', Creditors),
  (r'/reset', Reset),
  (r'/show', ShowDebts),
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()


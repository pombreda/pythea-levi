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
import crypt

from google.appengine.api.urlfetch import fetch

import re

from google.appengine.ext import db
from google.appengine.ext.db import polymodel
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from gaesessions import get_current_session

from StringIO import StringIO
from django.utils import simplejson
#import webapp2 as webapp

from google.appengine.ext.db import djangoforms as forms

class User(polymodel.PolyModel):
    userid = db.StringProperty()
    email = db.EmailProperty()
    display_name = db.TextProperty()
    password = db.ByteStringProperty()
    
    def set_password(self, password):
        self.password = crypt.crypt(password, os.urandom(2))

    def authenticate(self, password):
        return crypt.crypt(password, self.password) == self.password

# FIXME: Organisation also needs to be scoped to 
# a zipcode. E.g. woonbron delfshaven has a different mail address
# than woonbron ijsselmonde.
# FIXME: An organisation can also be a Bailiff for the real creditor.
# We need to be able to model this as well.
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

class ClientForm(forms.ModelForm):
    password = forms.StringProperty()
    class Meta:
        model = Client
        exclude = ['display_name', '_class', 'password']

class Category(db.Model):
    label = db.StringProperty()
    category = db.SelfReferenceProperty()

    def __str__(self):
        return self.label

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category

class Creditor(Organisation):
    category = db.ReferenceProperty(Category)

class CreditorForm(forms.ModelForm):
    class Meta:
        model = Creditor
        exclude = ['display_name', '_class', 'icon']

class Debt(db.Model):
    creditor = db.ReferenceProperty(Creditor)
    date = db.DateProperty()
    registration = db.DateProperty()
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
    'Overig': [
        'Boetes',
        'Belastingen',
        'Toeslagen',
        'Kinderopvang',
        'Deurwaarders'],
}

class Main(webapp.RequestHandler):
    def get(self):
        session = get_current_session()
        user = session.get('user')
        if not user:
            self.redirect('/login')
            return

        vars = { 'categories': categories,
                 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'main.html')
        self.response.out.write(template.render(path, vars))

class Register(webapp.RequestHandler):
    def get(self):
        f = ClientForm(self.request)
        self.response.out.write('<form method="post">')
        self.response.out.write(f.as_p())
        self.response.out.write('<p>Password: <input type="password" name="password" id="password"></p>')
        self.response.out.write('<p>Password (controle): <input type="password" name="password2" id="password2"></p>')
        self.response.out.write('<input type="submit">')
        self.response.out.write('</form>')
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'register.html')
        #self.response.out.write(template.render(path, vars))

    def post(self):
        # Read form variables and put the new user in the database
        f = ClientForm(self.request)
        if f.is_valid():
            #self.response.out.write(dir(f))
            new_user = f.save(commit=False)
            new_user._key_name = self.request.get('userid')
            # TODO: check
            # TODO: How can I add errors to a form?
            password1 = self.request.get('password')
            password2 = self.request.get('password2')
            if password1 != password2:
                print "Error: passwords do not match"
                print "Redisplay the form"
            else:
                new_user.set_password(self.request.get('password'))
                new_user.put()
                session['user'] = user
        else:
            self.response.out.write(f.is_valid())
            self.response.out.write(f.as_p())

class ResetPassword(webapp.RequestHandler):
    def get(self):
        # TODO: generate a new password:
        #   Communicate this via SMS, e-mail or account manager.
        path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
        self.response.out.write(template.render(path, vars))

class Login(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'login.html')
        self.response.out.write(template.render(path, vars))
  
    def post(self):
        userid = self.request.get('userid')
        passwd = self.request.get('password')
        self.response.out.write(userid)
        session = get_current_session()
        if session.is_active():
            session.terminate()
        try:
            user = User.get_by_key_name(userid)
            if not user.authenticate(passwd):
                self.response.out.write('Invalid password')
            else:
                self.response.out.write('Password okay, you are now logged in')
                session['user'] = user
        except Exception, e:
            logging.info("Error, probably user not found.")
            self.response.out.write(e)

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

class AddCompany(webapp.RequestHandler):
    def get(self):
        form = CreditorForm(self.request)
        path = os.path.join(os.path.dirname(__file__), 'templates', 'addcompany.html')
        vars = { 'form': form }
        self.response.out.write(template.render(path, vars))

    def post(self):
        form = CreditorForm(self.request)
        if form.is_valid():
            creditor = form.save(commit=True)
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'addcompany.html')
            vars = { 'form': form }
            self.response.out.write(template.render(path, vars))

class AddCategory(webapp.RequestHandler):
    def get(self):
        form = CategoryForm(self.request)
        path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
        vars = { 'form': form }
        self.response.out.write(template.render(path, vars))

    def post(self):
        form = CategoryForm(self.request)
        if form.is_valid():
            category = form.save(commit=True)
            path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
            vars = { 'form': form }
            self.response.out.write(template.render(path, vars))
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
            vars = { 'form': form }
            self.response.out.write(template.render(path, vars))

class ShowCategories(webapp.RequestHandler):
    def get(self):
         categories = Category.all()
         for category in categories:
             self.response.out.write(category.label + '<br>')
          
class ShowDebts(webapp.RequestHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'upload.html')
        self.response.out.write(template.render(path, vars))

application = webapp.WSGIApplication([
  (r'/', Main),
  (r'/register', Register),
  (r'/login', Login),
  (r'/enter', EnterDebts),
  (r'/upload', Upload),
  (r'/authorize', Authorize),
  (r'/crediteuren/(.*)', Creditors),
  (r'/addcompany', AddCompany),
  (r'/addcategory', AddCategory),
  (r'/categories', ShowCategories),
  (r'/reset', ResetPassword),
  (r'/show', ShowDebts),
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()


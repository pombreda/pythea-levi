from __future__ import with_statement
from google.appengine.dist import use_library
use_library('django', '1.2')
import os
import logging
import cgi
import datetime
import urllib
import csv
import pickle
import crypt
from StringIO import StringIO
import urlparse 
import re
import decimal

from google.appengine.ext import db
from google.appengine.ext.db import polymodel
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api.urlfetch import fetch
from google.appengine.api import mail
import wsgiref.handlers

from gaesessions import get_current_session

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
    display_name = db.StringProperty()
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
    state = db.StringProperty(default="NEW") # One of NEW, COMPLETED, APPROVED, DONE 
    approved = db.DateProperty()

    def hasDebt(self, creditor):
        for debt in self.debts:
            if debt.creditor.key().id() == creditor.key().id():
                return True

    def complete(self):
        self.state = "COMPLETED"
        self.put()

    def approve(self)
        self.state = "APPROVED"
        self.put()

class ClientForm(forms.ModelForm):
    password = forms.StringProperty()
    class Meta:
        model = Client
        exclude = ['display_name', '_class', 'password']

class TopCategory(db.Model):
    label = db.StringProperty()
    
    def __str__(self):
        return self.label

class TopCategoryForm(forms.ModelForm):
    class Meta:
        model = TopCategory

class Category(db.Model):
    label = db.StringProperty()
    topcategory = db.ReferenceProperty(TopCategory, collection_name='categories')

    def __str__(self):
        return self.label

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category

class Creditor(Organisation):
    category = db.ReferenceProperty(Category, collection_name='creditors')

class CreditorForm(forms.ModelForm):
    class Meta:
        model = Creditor
        exclude = ['display_name', '_class', 'icon']

class DecimalProperty(db.Property):
    data_type = decimal.Decimal

    def get_value_for_datastore(self, model_instance):
        return str(super(DecimalProperty, self).get_value_for_datastore(model_instance))

    def make_value_from_datastore(self, value):
        if value == None: return value
        return decimal.Decimal(value).quantize(decimal.Decimal('0.01'))

    def validate(self, value):
        value = super(DecimalProperty, self).validate(value)
        if value is None or isinstance(value, decimal.Decimal):
            return value
        elif isinstance(value, basestring):
            return decimal.Decimal(value)
        raise db.BadValueError("Property %s must be a Decimal or string." % self.name)

class Debt(db.Model):
    creditor = db.ReferenceProperty(Creditor)
    user = db.ReferenceProperty(Client, collection_name='debts')
    date = db.DateProperty()
    registration = db.DateProperty(auto_now_add=True)
    last_changed = db.DateProperty(auto_now=True)
    confirmation = db.DateProperty()
    amount = DecimalProperty(default=decimal.Decimal('0.00')) 

topcategories = TopCategory.all()
class Main(webapp.RequestHandler):
    def get(self):
        session = get_current_session()
        user = session.get('user')
        if not user:
            self.redirect('/login')
            return

        vars = { 'topcategories': topcategories,
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
                session = get_current_session()
                if session.is_active():
                    session.terminate()
                session['user'] = new_user
                self.redirect('/')
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

class Approve(webapp.RequestHandler):
    def get(self):
        users = Users.all()
        users.filter('status =', 'COMPLETED')
        vars = { 'users' : users }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'approve.html')
        self.response.out.write(template.render(path, vars))

class Creditors(webapp.RequestHandler):
    def get(self, id):
        session = get_current_session()
        user = session.get('user')
        category = Category.get_by_id(int(id))
        creditors = category.creditors
        vars = { 'topcategories': topcategories,
                 'creditors': creditors,
                 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'crediteuren.html')
        self.response.out.write(template.render(path, vars))
 
    def post(self, action):
        session = get_current_session()
        user = session.get('user')
        #keys = [ db.Key.from_path('Creditor', int(id)) for id in self.request.get_all('creditor') ]
        ids = [ int(id) for id in self.request.get_all('creditor') ]
        creditors = Creditor.get_by_id(ids)
        for creditor in creditors:
            if not user.hasDebt( creditor ):
                debt = Debt(creditor=creditor, user=user, registration=datetime.date.today())
                debt.put()
        self.redirect('/debts')

class AddCompany(webapp.RequestHandler):
    icon_re = re.compile(r'<link\s+rel=".*?icon"\s+href="(.*?)"', re.M | re.I)
    base_re = re.compile(r'<base\s+href="(.*?)"', re.M | re.I)
    def get(self):
        form = CreditorForm(self.request)
        path = os.path.join(os.path.dirname(__file__), 'templates', 'addcompany.html')
        vars = { 'form': form }
        self.response.out.write(template.render(path, vars))

    def post(self):
        form = CreditorForm(self.request)
        if form.is_valid():
            creditor = form.save(commit=False)
            # Maybe I should place this code inside the Creditor class itself?
            url = creditor.website
            homepage = fetch(url)
            base = self.base_re.search(homepage.content)
            if base:
                base = base.group(1)
            elif homepage.final_url:
                base = homepage.final_url
            else:
                base = url
            icon = self.icon_re.search(homepage.content)
            icon = icon.group(1) if icon else '/favicon.ico'
            icon_url = urlparse.urljoin(base, icon)
            creditor.icon = icon_url
            if not creditor.email:
                hostname = urlparse.urlparse(url).hostname
                if hostname.startswith('www'):
                    hostname = '.'.join(hostname.split('.')[1:])
                creditor.email = 'info@' + hostname
            if not creditor.display_name:
                hostname = urlparse.urlparse(url).hostname
                name = hostname.split('.')[-2]
                creditor.display_name = name
            creditor.put()
            self.redirect(self.request.url)
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
            self.redirect(self.request.url)
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
            vars = { 'form': form }
            self.response.out.write(template.render(path, vars))

class AddTopCategory(webapp.RequestHandler):
    def get(self):
        form = TopCategoryForm(self.request)
        path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
        vars = { 'form': form }
        self.response.out.write(template.render(path, vars))

    def post(self):
        form = TopCategoryForm(self.request)
        if form.is_valid():
            category = form.save(commit=True)
            self.redirect(self.request.url)
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
        session = get_current_session()
        user = session.get('user')
        vars = { 'topcategories': topcategories,
                 'user': user, }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'debts.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        session = get_current_session()
        user = session.get('user')
        if self.request.get('submit') == 'finish':
            self.redirect('/finished')
            mail.send_mail(sender="No reply <hans.then@gmail.com>",
                           to="<h.then@pythea.nl>",
                           subject="Dossier Entered",
                           body="Leeg")
            # Fixme, also mark that the user has finished data entry.
            # And make sure that the initial e-mail is sent only once.
            return

        for debt in user.debts:
            amount = decimal.Decimal(self.request.get(str(debt.key().id())))
            if amount and debt.amount != amount:
                debt.amount = amount
                debt.put()
                logging.info('Really different, write to database.')
            else:
                logging.info('Not really all that different, do not write to database.')
            if not amount:
                debt.delete()
        
        self.redirect('/debts')

class Finished(webapp.RequestHandler):
    def get(self):
        session = get_current_session()
        user = session.get('user')
        vars = { 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'finished.html')
        self.response.out.write(template.render(path, vars))

application = webapp.WSGIApplication([
  (r'/', Main),
  (r'/register', Register),
  (r'/login', Login),
  (r'/enter', EnterDebts),
  (r'/authorize', Authorize),
  (r'/crediteuren/(.*)', Creditors),
  (r'/debts', ShowDebts),
  (r'/finished', Finished),
  (r'/addcompany', AddCompany),
  (r'/addcategory', AddCategory),
  (r'/addtopcategory', AddTopCategory),
  (r'/categories', ShowCategories),
  (r'/reset', ResetPassword),
  (r'/show', ShowDebts),
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()


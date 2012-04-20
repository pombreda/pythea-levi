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

#from google.appengine.ext.db import polymodel
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template 

from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api.urlfetch import fetch
from google.appengine.api import mail
from google.appengine.ext import db
from google.appengine.api import images
from google.appengine.api import taskqueue

import wsgiref.handlers
import webob
from collections import defaultdict

from gaesessions import get_current_session

import simplejson as json

import models
import forms
import docs
import yaml

import inspect
import django

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, unicode):
                return obj.encode('utf-8', 'replace')
            elif isinstance(obj, models.decimal.Decimal):
                return str(obj)
            elif isinstance(obj, datetime.datetime):
                return str(obj)
            else:
                return json.JSONEncoder.default(self, obj)
        except Exception, e:
            return '--Could not encode object %s of type %s, because of %s--' % (str(obj), type(obj), e)

class BaseHandler(webapp.RequestHandler):
    def get_user(self):
        try:
            return self.session['user']
        except KeyError:
            return None

    def get_session(self):
        try:
            return get_current_session()
        except Exception:
            return None

    def dump(self):
        self.response.out.write('<table>')
        for key in self.request.arguments():
            self.response.out.write('<tr><td>%s</td><td>%s</td></tr>' % (key, self.request.get_all(key)))
        self.response.out.write('</table>')

    user = property(get_user)
    session = property(get_session)

    def render(self, vars, templ=None):
        #self.response.out.write('Session ' + str(self.session))
        if not template or 'application/json' in self.request.headers['Accept']: #or 'JSON' in self.session:
            self.response.headers['Content-Type'] = 'application/json'
            self.response.out.write(json.dumps(self.flatten(vars), cls=JSONEncoder, ensure_ascii=False))
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', templ)
            self.response.out.write(template.render(path, vars))
            self.response.out.write('<br>Template: %s<br>' % templ)
            js = json.dumps(self.flatten(vars), cls=JSONEncoder, ensure_ascii=False)
            self.response.out.write(js)

    def flatten(self, value):
        try:
            if isinstance(value, db.Model):
                return self.flatten_model(value)
            elif isinstance(value, django.forms.fields.Field):
                return self.flatten_field(value)
            elif isinstance(value, django.forms.widgets.Input):
                return self.flatten_widget(value)
            elif isinstance(value, list):
                return [ self.flatten(var) for var in value ] 
            elif isinstance(value, dict):
                return self.flatten_dict(value)
            elif isinstance(value, webob.multidict.UnicodeMultiDict):
                return self.flatten_mdict(value)
            elif forms == inspect.getmodule(value):
                return self.flatten_form(value)
            else:
                return value
        except Exception, e:
            return "error, could not flatten value %s, %s" % (value, e)

    def flatten_form(self, form):
        d = defaultdict(dict)
        for name, field in form.fields.items():
            for attr in ['min_length', 'max_length', 'initial', 'required', 'label', 'help_text', 'show_hidden_initial']:
                if attr in field.__dict__:
                    d[name][attr] = field.__dict__[attr]
                if hasattr(field.widget, 'input_type'):
                    d[name]['input_type'] = field.widget.input_type
                elif hasattr(field.widget, 'choices'):
                    d[name]['input_type'] = 'select'
                d[name]['is_hidden'] = field.widget.is_hidden
            if name in form.data and field.widget.input_type != 'password':
                d[name]['value'] = form.data[name]
            if name in form.errors:
                d[name]['value'] = form.errors[name]
        r = {'fields': d } 
        if '__all__' in form.errors:
            r['errors'] = form.errors['__all__']
        return r

    def flatten_widget(self, widget):
        d = {}
        #for attr in ['min_length', 'max_length', 'initial', 'required', 'label', 'help_text', 'error_messages', 'show_hidden_initial']:
        #    d[attr] = field.__dict__[attr]
        #return d
        return dir(widget)
 
    def flatten_mdict(self, vars):
        d = defaultdict(list)
        for key, value in vars.items():
            d[key].append(self.flatten(value))
        return d

    def flatten_dict(self, vars):
        d = {}
        for key, value in vars.items():
            d[key] = self.flatten(value)
        return d

    def flatten_model(self, model):
        d = {}
        for key, value in model.__dict__['_entity'].items():
            d[key] = self.flatten(value)
        return d

class Main(BaseHandler):
    def get(self):
        """Show the default screen. This is now the login screen"""
        user = self.user
        if not user:
            self.redirect('/login')
            return
        self.session['JSON'] = False

        vars = { 
                 'user': user }
        self.render(vars, 'main.html')

class Screens(BaseHandler):
    def get(self):
        """A utility screen to display all screens inside the application"""
        doc = docs.Document(application, self)
        self.render( {'docs': doc.docs, 'tree': dict(doc.tree)}, 'screens.html' )
        #self.response.out.write( application._url_mapping )
 
class ClientNew(BaseHandler):
    def get(self):
        """Show the form to add a new client"""
        form = forms.ClientForm()
        form.title = 'Registreer'
        vars = { 'forms': [form] , 'title': 'Registreer'}
        self.render(vars, 'form.html')

    def post(self):
        """Enter the new client"""
        # Read form variables and put the new user in the database
        form = forms.ClientForm(self.request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)
            new_user.set_password(form.cleaned_data['password1'])
            new_user.put()
            session = get_current_session()
            if session.is_active():
                session.terminate()
            session['user'] = new_user
            self.redirect('/client/contact')
        else:
            vars = { 'forms': [form], 'title': 'Registreer'}
            self.render(vars, 'form.html')


class ClientContact(BaseHandler):
    def get(self):
        """Show a list of possible contact persons"""
        user = self.user
        zipcode = user.zipcode
        orgs = [ i for i in models.SocialWork.all() if i.accepts(zipcode)]
        vars = { 'user': user,
                 'organisations': orgs, 
                 'title': 'Met wie heeft u gesproken?' }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'addcontact.html')
        self.render(vars, 'addcontact.html')
                
    def post(self):
        """Add the selected contact person to the database"""
        key = self.request.get('selected')
        user = self.user
        contact = models.SocialWorker.get(key)
        user.contact = contact
        user.put()
        self.redirect('/client/creditors')


class ClientSelectCreditors(BaseHandler):
    def get(self):
        """Show a list of available creditors
 
        FIXME: we should change this, to show the available creditors per category.
        """
        user = self.user
        creditors = list(models.Creditor.all())
        creditors.reverse()
        for creditor in creditors:
            creditor.selected = user.hasCreditor(creditor)
        vars = { 
                 'creditors': creditors,
                 'user': user }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'crediteuren.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'crediteuren.html')
 
    def post(self):
        """Add the selected creditors to the database"""
        user = self.user
        selected_ids = [ int(id) for id in self.request.get_all('selected') ]
        visible_ids = [ int(id) for id in self.request.get_all('visible') ]
        creditors = models.Creditor.get_by_id(visible_ids)
        for creditor in creditors:
            if creditor.key().id() in selected_ids:
                user.addCreditor(creditor)
            else:
                user.removeCreditor(creditor)
        action = self.request.get('action')
        if action == 'opslaan':
            self.redirect('/client/creditors')
        else:
            self.redirect('/client/validate')


class ClientCreditorsNew(BaseHandler):
    def get(self):
        """Add a new creditor that is specific to this client
 
        FIXME:
        The new creditor will have status provisional, until it is validated by the SocialWorker"""
        user = self.user
        form = forms.CreditorForm(self.request.POST)
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'addcompany.html')
        #vars = { 'form': form }
        vars = { 'forms': [form] }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'form.html')

    def post(self):
        """Add the creditor to the database"""
        form = forms.CreditorForm(self.request.POST)
        if form.is_valid():
            creditor = form.save(commit=False)
            creditor.expand()
            creditor.put()
            self.redirect('todo.html')
        else:
            vars = { 'forms': [form] }
            self.render(vars, 'form.html')


class ClientValidate(BaseHandler):
    def get(self):
        """Validate a new client"""
        user = self.user
        vars = { 
                 'user': user }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'clientvalidate.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'clientvalidate.html')

    def post(self):
        action = self.request.get('action')
        if action == 'correct':
            user = self.user
            user.complete()
            mail.send_mail(sender="No reply <hans.then@gmail.com>",
                           to="<h.then@pythea.nl>",
                           subject="Dossier Entered",
                           body="Dossier is toegevoegd voor %s %s" % (user.first_name, user.last_name))

            # FIXME: also mark that the user has finished data entry.
            # And make sure that the initial e-mail is sent only once.
        
            self.redirect('/client/submitted')
        else:
            self.redirect('/client/creditors')
       

class ClientSubmitted(BaseHandler):
    def get(self):
        user = self.get_user()
        message = 'De gegevens worden naar uw maatschappelijk werker gestuurd voor controle.'
        vars = { 'user': user,
                 'message': message }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'message.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'message.html')


class ClientDebts(BaseHandler):
    def get(self):
        user = self.get_user()
        vars = { 'user': user }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebts.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'clientdebts.html')

    def post(self):
        user = self.get_user()
        message = 'U bent klaar'
        vars = { 'user': user,
                 'message': message }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'message.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'message.html')
 


class ClientDebtsAdd(BaseHandler):
    def get(self, creditor):
        user = self.get_user()
        creditor = models.CreditorLink.get_by_id(int(creditor))
        form = forms.DebtForm()
        vars = { 'user': user,
                 'creditor': creditor,
                 'form': form }
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebtsadd.html')
        #self.response.out.write(template.render(path, vars))
        self.render(vars, 'clientdebtsadd.html')

    def post(self, creditor):
        user = self.get_user()
        form = forms.DebtForm(self.request.POST)
        creditor = models.CreditorLink.get_by_id(int(creditor))
        if form.is_valid():
            logging.error("valid")
            new_debt = form.save(commit=False)
            new_debt.creditor = creditor
            new_debt.put()
            self.redirect(self.request.url)
        else:
            logging.error("error")
            logging.error( form.non_field_errors() )
            errors = [ (field.name, field.errors) for field in form ]
            logging.error( errors )

            vars = { 'user': user,
                     'creditor': creditor,
                     'form': form }
            self.render(vars, 'clientdebtsadd.html')
            #path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebtsadd.html')
            #self.response.out.write(template.render(path, vars))


class ClientDebtsSelectCreditor(BaseHandler):
    """This is used to select a 'deurwaarder' for a debt (or a creditor in case of a 'deurwaarder'"""
    def get(self):
        user = self.get_user()
        creditors = models.Creditor.all()
      
        vars = { 'user': user,
                 'creditors': creditors }
        self.render(vars, 'clientdebtsselectcreditor.html')
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebtsselectcreditor.html')
        #self.response.out.write(template.render(path, vars))
        

class OrganisationNew(BaseHandler):
    def get(self):
        form1 = forms.SocialWorkForm(prefix='f1')
        form2 = forms.SocialWorkerForm(prefix='f2')
        form1.title = 'Organisatie'
        form2.title = 'Contactpersoon'
        vars = { 'forms': [form1, form2] , 'title': 'Registreer Hulpverleningsorganisatie'}
        self.render(vars, 'form.html')

    def post(self):
        # Read form variables and put the new user in the database
        photo = self.request.get('f2-photo')
        form1 = forms.SocialWorkForm(self.request.POST, prefix='f1')
        form2 = forms.SocialWorkerForm(self.request.POST, prefix='f2')
        form1.title = 'Organisatie'
        form2.title = 'Contactpersoon'
        if form1.is_valid():
            organisation = form1.save(commit=False)
            organisation.put()
            the_user = form2.save(commit=False)
            the_user.set_password(form2.cleaned_data['password1'])
            the_user.organisation = organisation
            # FIXME: we should have an intermediate step to
            # retrieve the crop data for the image.
            # Size should be approximately 80x80 pixels
                 
            if photo:
                # Resize the image
                image = images.Image(image_data=photo)
                the_user.photo = db.Blob(photo)

            the_user.put()
            session = get_current_session()
            if session.is_active():
                session.terminate()
            session['user'] = the_user
            self.redirect('/organisation/employees')
        else:
            #path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            vars = { 'forms': [form1, form2] , 'title': 'Registreer Hulpverleningsorganisatie'}
            #self.response.out.write(template.render(path, vars))
            self.render(vars, 'form.html')


class OrganisationEmployeesList(BaseHandler):
    def get(self):
        user = self.user
        organisation = user.organisation
#        employees = [ employee for employee in organisation.employees if employee.key != user.key ]
        employees = organisation.employees

        vars = { 'user': user, 'organisation': organisation, 'employees': employees }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'listemployees.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        action = self.request.get('action')
        if action == 'Create':
            self.redirect('/organisation/employees/new')
        elif action == 'Delete':
            logging.exception('FIXME: employee/deletion not implemented')
            self.redirect('/organisation/employees')
        else:
            raise Exception('Invalid action %s' % action)


class Photo(BaseHandler):
    def get(self, key):
        """Return the photo for employee with KEY"""
        employee = models.SocialWorker.get(key)
        if (employee and employee.photo):
            self.response.headers['Content-Type'] = 'image/jpeg'
            self.response.out.write(employee.photo)
        else:
            # TODO:
            self.redirect('/images/nopassphoto.gif')


class OrganisationEditEmployee(BaseHandler):
    """Create or edit an existing employee"""
    def get(self, key=None):
        user = self.user
        organisation = user.organisation
        if key:
            employee = models.SocialWorker.get(key)
            form = forms.SocialWorkerForm(instance=employee)	
        else:
            form = forms.SocialWorkerForm()
        vars = { 'forms': [form] }

        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))


    def post(self, key=None):
        # Read form variables and put the new user in the database
        user = self.user
        organisation = user.organisation
        if key:
            instance = models.SocialWorker.get(key)
            form = forms.SocialWorkerForm(self.request.POST, instance=instance)
        else:
            form = forms.SocialWorkerForm(self.request.POST)
            
        photo = self.request.get('photo')
        if form.is_valid():
            employee = form.save(commit=False)
            # FIXME: this password code can happen in the form class
            employee.set_password(form.cleaned_data['password1']) 
            employee.organisation = organisation
            if photo:
                image = images.Image(image_data=photo)
                employee.photo = db.Blob(photo)
            employee.put()
            self.redirect('/organisation/employees')
            """
            if image.height != 80 and image.width != 80:
                self.redirect('/organisation/employees/resize/%s' % employee.key())
            else:
                self.redirect('/organisation/employees')
            """
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            vars = { 'forms': [form], 'title': 'Registreer'}
            self.response.out.write(template.render(path, vars))

class OrganisationEmployeeResize(BaseHandler):
    def get(self, key):
        worker = models.SocialWorker.get(key)
        vars = { 'worker': worker }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'resize.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        #self.response.headers['Content-Type'] = 'image/jpeg'
        self.response.headers['Content-Type'] = 'text/plain'
        x1 = float(self.request.get('x'))
        x2 = float(self.request.get('x2'))
        y1 = float(self.request.get('y'))
        y2 = float(self.request.get('y2'))
 
        worker = models.SocialWorker.get(key)
        vars = { 'worker': worker }
        image = images.Image(image_data=worker.photo)
        image.crop( x1 / image.width,
                    y1 / image.height,
                    x2 / image.width,
                    y2 / image.height )

        image = image.execute_transforms(output_encoding=images.JPEG)
        worker.photo = image
        worker.put()
        self.redirect(self.request.url)
            
        #self.dump()

class OrganisationZipcodes(BaseHandler):
    """TODO:"""
    def get(self):
        session = get_current_session()
        user = session.get('user')
        zipcodes = ','.join(user.organisation.zipcodes)
        vars = { 'user': user , 'zipcodes': zipcodes}
        path = os.path.join(os.path.dirname(__file__), 'templates', 'selectzipcodes.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        zipcodes = self.request.get('zipcodes')
        zipcodes = zipcodes.replace(' ', '')
        zipcodes = zipcodes.split(',')
        user = self.user
        user.organisation.zipcodes = zipcodes
        user.organisation.put()
        self.redirect(self.request.url)
        

class Todo(BaseHandler):
    def get(self):
        self.response.out.write("TODO: URL is valid, but not implemented")


class ResetPassword(BaseHandler):
    def get(self):
        if not self.user or not self.user.is_superuser:
            self.response.out.write("User: %s Not authenticated. %s" % (self.user.first_name, self.user.is_superuser))
            return
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'resetpasswd.html')
            self.response.out.write(template.render(path, vars))

    def post(self):
        # TODO: generate a new password:
        #   Communicate this via SMS, e-mail or account manager.
        userid = self.request.get('userid')
        newpasswd = self.request.get('passwd')
        user_key = db.Key.from_path("User", userid)
        user = models.User.get(user_key)
        user.set_password(newpasswd)
        user.put()
        self.response.out.write("Done")


class Login(BaseHandler):
    def get(self):
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'login.html')
        #self.response.out.write(template.render(path, vars))
        self.render({}, 'login.html')
  
    def post(self):
        userid = self.request.get('userid')
        passwd = self.request.get('password')
        session = get_current_session()
        if session.is_active():
            session.terminate()
        try:
            user = models.User.get_by_key_name(userid)
            if user and user.authenticate(passwd):
                session['user'] = user
                self.redirect(user.start_page())
            else:
                vars = { 'message': 'Gebruikersnaam of wachtwoord is ongeldig.' }
                self.render(vars, 'login.html')
        except Exception, e:
            logging.info("Error, probably user not found.")
            self.response.out.write(e)


class EmployeeApprovals(BaseHandler):
    def get(self):
        clients = models.Client.all()
        clients.filter('state =', 'COMPLETED')
        vars = { 'clients' : clients }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'employeeapprovals.html')
        self.response.out.write(template.render(path, vars))


class EmployeeWaiting(BaseHandler):
    def get(self):
        state = self.request.get('state')
        if not state: state = 'APPROVED'
        clients = models.Client.all()
        clients.filter('state =', state)
        vars = { 'state': state,
                 'clients' : clients }

        path = os.path.join(os.path.dirname(__file__), 'templates', 'employeeapprovals.html')
        self.response.out.write(template.render(path, vars))


class EmployeeApprove(BaseHandler):
    def get(self, client):
        client = models.Client.get_by_key_name(client)
        vars = { 'client' : client }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'employeeapprove.html')
        self.response.out.write(template.render(path, vars))

    def post(self, client):
        client = models.Client.get_by_key_name(client)
        for creditor in client.creditors:
            # send mail to the creditor (or the Bailiff for this creditor)
            pass
        client.approve()
        message = 'We zouden hier mails moeten versturen naar crediteuren, maar ik heb nog een voorbeeldbrief nodig. Hans'
        vars = { 'client' : client,
                 'message' : message }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'message.html')
        self.response.out.write(template.render(path, vars))


class EmployeeBecome(BaseHandler):
    def get(self, client = None):
        if not client:
            clients = models.User.all()
            vars = { 'clients' : clients }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'employeebecomeclients.html')
            self.response.out.write(template.render(path, vars))
        else:
            client = urllib.unquote(client)
            logging.debug(client)
            user = models.User.get_by_key_name(client)
            if not user:
                self.redirect(self.request.url)
            else:
                logging.debug(user)
                start_page = user.start_page()
                logging.debug(start_page)
                session = get_current_session()
                if session.is_active():
                    session.terminate()
                session['user'] = user
                self.redirect(start_page)

class AddCompany(BaseHandler):
    def get(self):
	"""Show a form to enter a new creditor"""
	form = forms.CreditorForm(self.request.POST)
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        """Add the new creditor"""
        form = forms.CreditorForm(self.request.POST)
        if form.is_valid():
            creditor = form.save(commit=False)
            creditor.expand()
            creditor.put()
            self.redirect(self.request.url)
        else:
            vars = { 'forms': [form] }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            self.response.out.write(template.render(path, vars))


class AddCategory(BaseHandler):
    def get(self):
        """Show a list of existing categories"""
        form = forms.CategoryForm(self.request)
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        """Add a new category"""
        form = forms.CategoryForm(self.request)
        if form.is_valid():
            category = form.save(commit=True)
            self.redirect(self.request.url)
        else:
            vars = { 'forms': [form] }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            self.response.out.write(template.render(path, vars))
            # path = os.path.join(os.path.dirname(__file__), 'templates', 'addcategory.html')
            # vars = { 'form': form }
            # self.response.out.write(template.render(path, vars))


class ShowCategories(BaseHandler):
    def get(self):
         categories = Category.all()
         for category in categories:
             self.response.out.write(category.label + '<br>')

          
class EnterCreditors(BaseHandler):
    """Does not appear to be in use"""
    def get(self):
        """Show a list of possible creditors"""
        session = get_current_session()
        user = session.get('user')
        vars = { 
                 'user': user, }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientcreditors.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        """Write the selected creditors to the database"""
        session = get_current_session()
        user = session.get('user')
        for creditor in user.creditors:
            amount = decimal.Decimal(self.request.get(str(creditor.key().id())))
            if creditor.estimated_amount != amount:
                creditor_estimated.amount = amount
                creditor.put()
                logging.info('Really different, write to database.')
            else:
                logging.info('Not really all that different, do not write to database.')
        
        self.redirect('/debts')


class Initialize(BaseHandler):
    def get(self):
        taskqueue.add(url='/task/init')


class Test(BaseHandler):
    """I use this to test new code"""
    def get(self):
        """Show the test response"""
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'test.html')
        #self.response.out.write(template.render(path, vars))
        self.response.headers['Content-Type'] = 'text/plain'
        #self.response.out.write(self.request.accept)
        self.dump()

    def post(self):
        """Testing the code to resize a passphoto"""
        #self.response.headers['Content-Type'] = 'image/jpeg'
        self.response.headers['Content-Type'] = 'text/plain'
        x1 = float(self.request.get('x'))
        x2 = float(self.request.get('x2'))
        y1 = float(self.request.get('y'))
        y2 = float(self.request.get('y2'))
 
        with open('nopassphoto.gif') as file:
            image = images.Image(image_data=file.read())
        image.crop( x1 / image.width,
                    y1 / image.height,
                    x2 / image.width,
                    y2 / image.height )

        image = image.execute_transforms(output_encoding=images.JPEG)
        self.response.out.write(image)
            
        #self.dump()

class TaskInitialize(BaseHandler):
    def get(self):
        logging.info(str(self.request.url))
        taskqueue.add(url='/task/init')

    def post(self):
        """Background task to initialize the database with a list of clients and creditors"""
        try:
            client = models.Client(key_name='hans.then', username='clientXX', first_name='client', 
                                   last_name='XX', email='hans.then@gmail.com', 
                                   address='Rochussenstraat 347a', zipcode='3023 HE',
                                   city='Rotterdam', mobile='+31634751204')
            client.set_password('XX')
            client.put()
        except:
            logging.info('Error creating client')
        
        try:
            contact = models.SocialWorker(key_name='hans.then@gmail.com', username='medewerkerXX', first_name='mw', 
                                          last_name='XX', email='hans.then@gmail.com')
            contact.set_password('XX')
            contact.put()
            organisation = models.Organisation('SMDD', display_name='SMDD', website='http://www.smdd.nl',
                                               email='info@smdd.nl', address='Havenstraat 80',
                                               zipcode='2300', city='Rotterdam', contact=contact)
            organisation.put()
        except Exception, e:
            logging.info('Error creating organisation')
            logging.info(e)
   
        return

        with open('schuldeisers.txt') as file:
            for line in file:
                website, display_name = line.strip().split(None,1)
                q = db.Query(models.Organisation, keys_only = True)
                q.filter('display_name =', display_name)
                if q.fetch(1):
                    logging.info('%s,%s Already done' % (website, display_name))
                    continue
                else:
                    logging.info('%s,%s' % (website, display_name))
                    website = 'http://' + website
                    creditor = models.Creditor(website=website, 
                                               display_name=display_name)
                    try:
                        creditor.expand()
                        creditor.put()
                    except Exception, e:
                        logging.info( "Failed to put %s %s" % (display_name, e) )
                        
 

application = webapp.WSGIApplication([
# Anonymous
  (r'/', Main),
  (r'/login', Login),
  (r'/reset', ResetPassword),

# Admin functions
  (r'/admin/init', TaskInitialize),
  (r'/admin/screens', Screens),
#  (r'/finished', Finished),
  (r'/admin/company/new', AddCompany),
  (r'/admin/category/new', AddCategory),
#  (r'/addemployees', AddEmployees),
  (r'/admin/category/list', ShowCategories),
  (r'/admin/test', Test),
  (r'/admin/become/client/(.*)', EmployeeBecome),
  (r'/admin/become', EmployeeBecome),

# Background tasks
#  (r'/task/init', TaskInitialize),

# The register client use case
  (r'/client/register', ClientNew),
  (r'/client/register/contact', ClientContact),
  (r'/client/register/creditors/new', ClientCreditorsNew),
  (r'/client/register/creditors', ClientSelectCreditors),
  (r'/client/register/validate', ClientValidate),
  (r'/client/register/submitted', ClientSubmitted), # FIXME: this is more of a confirmation message than a 
                                           # real GET/POST
# The clients edit debts use case
  (r'/client/debts/list', ClientDebts),
  (r'/client/debts/add/(.*)', ClientDebtsAdd),
  (r'/client/debts/creditor/select', ClientDebtsSelectCreditor),

# The register organisation use case
  (r'/organisation/register', OrganisationNew),
  (r'/organisation/employees', OrganisationEmployeesList),
  (r'/organisation/register/zipcodes', OrganisationZipcodes), #FIXME:
  (r'/organisation/employees/add', OrganisationEditEmployee),
  (r'/organisation/employees/edit/(.*)', OrganisationEditEmployee),
  (r'/organisation/employees/resize/(.*)', OrganisationEmployeeResize),
  (r'/employee/photo/(.*)', Photo),

# Several employee use cases
  (r'/employee/handle/approvals', EmployeeWaiting),
  (r'/employee/handle/waiting', EmployeeWaiting),
  (r'/employee/handle/approve/(.*)', EmployeeApprove),
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()


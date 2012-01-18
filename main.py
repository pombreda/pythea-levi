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

import wsgiref.handlers

from gaesessions import get_current_session

from django.utils import simplejson

import models
import forms

class BaseHandler(webapp.RequestHandler):
    def get_user(self):
        try:
            return get_current_session()['user']
        except KeyError:
            return None

    user = property(get_user)

class Main(BaseHandler):
    def get(self):
        user = self.user
        if not user:
            self.redirect('/login')
            return

        vars = { 
                 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'main.html')
        self.response.out.write(template.render(path, vars))


class ClientNew(BaseHandler):
    def get(self):
        form = forms.ClientForm()
        form.title = 'Registreer'
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        vars = { 'forms': [form] , 'title': 'Registreer'}
        self.response.out.write(template.render(path, vars))

    def post(self):
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
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            vars = { 'forms': [form], 'title': 'Registreer'}
            self.response.out.write(template.render(path, vars))

class ClientContact(BaseHandler):
    def get(self):
        user = self.user
        zipcode = user.zipcode
        orgs = [ i for i in models.SocialWork.all() if i.accepts(zipcode)]
        vars = { 'user': user,
                 'organisations': orgs, 
                 'title': 'Met wie heeft u gesproken?' }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'addcontact.html')
        self.response.out.write(template.render(path, vars))
                
    def post(self):
        key = self.request.get('selected')
        user = self.user
        contact = models.SocialWorker.get(key)
        user.contact = contact
        user.put()
        self.redirect('/client/creditors')


class ClientSelectCreditors(BaseHandler):
    def get(self):
        user = self.user
        creditors = list(models.Creditor.all())
        creditors.reverse()
        for creditor in creditors:
            creditor.selected = user.hasCreditor(creditor)
        vars = { 
                 'creditors': creditors,
                 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'crediteuren.html')
        self.response.out.write(template.render(path, vars))
 
    def post(self):
        # FIXME: does not uncheck creditors that have been "unselected"
        user = self.user
        #keys = [ db.Key.from_path('Creditor', int(id)) for id in self.request.get_all('creditor') ]
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

class ClientValidate(BaseHandler):
    def get(self):
        user = self.user
        vars = { 
                 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientvalidate.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        action = self.request.get('action')
        if action == 'correct':
            user = self.user
            user.complete()
            mail.send_mail(sender="No reply <hans.then@gmail.com>",
                           to="<h.then@pythea.nl>",
                           subject="Dossier Entered",
                           body="Dossier is toegevoegd voor %s %s" % (user.first_name, user.last_name))

            # Fixme, also mark that the user has finished data entry.
            # And make sure that the initial e-mail is sent only once.
        
            self.redirect('/client/submitted')
        else:
            self.redirect('/client/creditors')
       

class ClientSubmitted(BaseHandler):
    def get(self):
        session = get_current_session()
        user = session.get('user')
        vars = { 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'finished.html')
        self.response.out.write(template.render(path, vars))


class OrganisationNew(BaseHandler):
    def get(self):
        form1 = forms.SocialWorkForm(prefix='f1')
        form2 = forms.SocialWorkerForm(prefix='f2')
        form1.title = 'Organisatie'
        form2.title = 'Contactpersoon'
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        vars = { 'forms': [form1, form2] , 'title': 'Registreer Hulpverleningsorganisatie'}
        self.response.out.write(template.render(path, vars))

    def post(self):
        # Read form variables and put the new user in the database
        logging.info(self.request.arguments())
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
                image.crop( 0.0 / image.width,
                            0.0 / image.height,
                           80.0 / image.width,
                           80.0 / image.width )
                photo = image.execute_transforms(image.format)
                the_user.photo = db.Blob(photo)

            the_user.put()
            session = get_current_session()
            if session.is_active():
                session.terminate()
            session['user'] = the_user
            self.redirect('/organisation/employees')
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            vars = { 'forms': [form1, form2] , 'title': 'Registreer Hulpverleningsorganisatie'}
            self.response.out.write(template.render(path, vars))


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
        employee = models.SocialWorker.get(key)
        if (employee and employee.photo):
            self.response.headers['Content-Type'] = 'image/jpeg'
            self.response.out.write(employee.photo)
        else:
            # TODO:
            self.redirect('/images/nopassphoto.gif')

class OrganisationEditEmployee(BaseHandler):
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
            try:
                image = images.Image(image_data=photo)
                employee.photo = db.Blob(photo)
            except TypeError, e:
                pass #Ignore when no photo is set.

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


class OrganisationZipcodes(BaseHandler):
    """TODO:"""
    def get(self):
        session = get_current_session()
        user = session.get('user')
        vars = { 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'selectzipcodes.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        pass
        

class Todo(BaseHandler):
    def get(self):
        self.response.out.write("TODO: URL is valid, but not implemented")


class ResetPassword(BaseHandler):
    def get(self):
        # TODO: generate a new password:
        #   Communicate this via SMS, e-mail or account manager.
        path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
        self.response.out.write(template.render(path, vars))


class Login(BaseHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'login.html')
        self.response.out.write(template.render(path, vars))
  
    def post(self):
        userid = self.request.get('userid')
        passwd = self.request.get('password')
        session = get_current_session()
        if session.is_active():
            session.terminate()
        try:
            user = models.User.get_by_key_name(userid)
            if not user.authenticate(passwd):
                self.response.out.write('Invalid password')
            else:
                self.response.out.write('Password okay, you are now logged in')
                self.response.out.write('<p><a href="/debts">Klik hier om verder te gaan</a>')
                session['user'] = user
        except Exception, e:
            logging.info("Error, probably user not found.")
            self.response.out.write(e)


class EmployeeApprovals(BaseHandler):
    def get(self):
        clients = models.Client.all()
        clients.filter('state =', 'COMPLETED')
        vars = { 'clients' : clients }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'listapprove.html')
        self.response.out.write(template.render(path, vars))


class EmployeeApprove(BaseHandler):
    def get(self, client):
        client = models.Client.get_by_key_name(client)
        vars = { 'client' : client }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'approve.html')
        self.response.out.write(template.render(path, vars))

    def post(self, client):
        client = models.Client.get_by_key_name(client)
        for debt in client.debts:
            # send mail to the creditor (or the Bailiff for this creditor)
            pass
        vars = { 'client' : client }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'approve.html')
        self.response.out.write(template.render(path, vars))



class AddCompany(BaseHandler):
    icon_re = re.compile(r'<link\s+rel=".*?icon"\s+href="(.*?)"', re.M | re.I)
    base_re = re.compile(r'<base\s+href="(.*?)"', re.M | re.I)
    keywords_re = re.compile(r'<meta\s+name="keywords"\s+content=["\'](.*?)["\']')
    def get(self):
        form = forms.CreditorForm(self.request.POST)
        #path = os.path.join(os.path.dirname(__file__), 'templates', 'addcompany.html')
        #vars = { 'form': form }
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        form = forms.CreditorForm(self.request.POST)
        if form.is_valid():
            creditor = form.save(commit=False)
            # Maybe I should place this code inside the Creditor class itself?
            url = creditor.website
            homepage = fetch(url)
            base = self.base_re.search(homepage.content)
            if base:
                base = base.group(1)
            elif homepage.final_url:
                if homepage.final_url.startswith('/'):
                    base = url + homepage.final_url
                else:
                    base = homepage.final_url
            else:
                base = url
            icon = self.icon_re.search(homepage.content)
            icon = icon.group(1) if icon else '/favicon.ico'
            icon_url = urlparse.urljoin(base, icon)
            keywords = self.keywords_re.search(homepage.content)
            keywords = keywords.group(1) if keywords else ""
            keywords = keywords.split(',')
            creditor.tags = keywords
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
            # path = os.path.join(os.path.dirname(__file__), 'templates', 'addcompany.html')
            # vars = { 'form': form }
            # self.response.out.write(template.render(path, vars))
            vars = { 'forms': [form] }
            path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
            self.response.out.write(template.render(path, vars))


class AddCategory(BaseHandler):
    def get(self):
        form = forms.CategoryForm(self.request)
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
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
    def get(self):
        session = get_current_session()
        user = session.get('user')
        vars = { 
                 'user': user, }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientcreditors.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
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


application = webapp.WSGIApplication([
  (r'/', Main),
  (r'/login', Login),
  (r'/client/new', ClientNew),
  (r'/client/contact', ClientContact),
  (r'/client/creditors', ClientSelectCreditors),
  (r'/client/validate', ClientValidate),
  (r'/client/submitted', ClientSubmitted),
  (r'/client/debts', Todo),
  (r'/organisation/new', OrganisationNew),
  (r'/organisation/employees', OrganisationEmployeesList),
  (r'/organisation/employees/new', OrganisationEditEmployee),
  (r'/organisation/employees/edit/(.*)', OrganisationEditEmployee),
  (r'/organisation/zipcodes', OrganisationZipcodes),
  (r'/employee/photo/(.*)', Photo),
  (r'/employee/approvals', EmployeeApprovals),
  (r'/employee/approve/(.*)', EmployeeApprove),
#  (r'/finished', Finished),
  (r'/company/new', AddCompany),
  (r'/category/new', AddCategory),
#  (r'/addemployees', AddEmployees),
  (r'/category/list', ShowCategories),
  (r'/reset', ResetPassword),
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()


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

    def dump(self):
        self.response.out.write('<table>')
        for key in self.request.arguments():
            self.response.out.write('<tr><td>%s</td><td>%s</td></tr>' % (key, self.request.get(key)))
        self.response.out.write('</table>')

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
        user = self.user
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
            creditor.expand()
            creditor.put()


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
        path = os.path.join(os.path.dirname(__file__), 'templates', 'message.html')
        self.response.out.write(template.render(path, vars))


class ClientDebts(BaseHandler):
    def get(self):
        user = self.get_user()
        vars = { 'user': user }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebts.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
        user = self.get_user()
        message = 'U bent klaar'
        vars = { 'user': user,
                 'message': message }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'message.html')
        self.response.out.write(template.render(path, vars))
 


class ClientDebtsAdd(BaseHandler):
    def get(self, creditor):
        user = self.get_user()
        creditor = models.CreditorLink.get_by_id(int(creditor))
        form = forms.DebtForm()
        vars = { 'user': user,
                 'creditor': creditor,
                 'form': form }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebtsadd.html')
        self.response.out.write(template.render(path, vars))

    def post(self, creditor):
        user = self.get_user()
        form = forms.DebtForm(self.request.POST)
        creditor = models.CreditorLink.get_by_id(int(creditor))
        logging.error("We are here")
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
            path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebtsadd.html')
            self.response.out.write(template.render(path, vars))


class ClientDebtsSelectCreditor(BaseHandler):
    """This is used to select a 'deurwaarder' for a debt (or a creditor in case of a 'deurwaarder'"""
    def get(self):
        user = self.get_user()
        creditors = models.Creditor.all()
      
        vars = { 'user': user,
                 'creditors': creditors }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'clientdebtsselectcreditor.html')
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
            if user and user.authenticate(passwd):
                session['user'] = user
                self.redirect(user.start_page())
            else:
                path = os.path.join(os.path.dirname(__file__), 'templates', 'login.html')
                vars = { 'message': 'Gebruikersnaam of wachtwoord is ongeldig.' }
                self.response.out.write(template.render(path, vars))
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
        clients = models.Client.all()
        clients.filter('state =', 'APPROVED')
        vars = { 'clients' : clients }

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
    def get(self):
        clients = models.Client.all()
        vars = { 'clients' : clients }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'employeebecomeclients.html')
        self.response.out.write(template.render(path, vars))
        
    def post(self, client):
        client = models.Client.get_by_key_name(client)
        session['user'] = client
        self.redirect('/client/creditors')

class AddCompany(BaseHandler):
    def get(self):
        form = forms.CreditorForm(self.request.POST)
        vars = { 'forms': [form] }
        path = os.path.join(os.path.dirname(__file__), 'templates', 'form.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
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


class Initialize(BaseHandler):
    def get(self):
        taskqueue.add(url='/task/init')


class Test(BaseHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), 'templates', 'test.html')
        self.response.out.write(template.render(path, vars))

    def post(self):
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
    def post(self):
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
                    creditor.expand()
                    try:
                        creditor.put()
                    except e:
                        logging.info( "Failed to put %s %s" % (display_name, e) )
                        print e
 

application = webapp.WSGIApplication([
  (r'/', Main),
  (r'/init', Initialize),
  (r'/task/init', TaskInitialize),
  (r'/login', Login),

# The register client use case
  (r'/client/new', ClientNew),
  (r'/client/contact', ClientContact),
  (r'/client/creditors/new', ClientCreditorsNew),
  (r'/client/creditors', ClientSelectCreditors),
  (r'/client/validate', ClientValidate),
  (r'/client/submitted', ClientSubmitted), # FIXME: this is more of a confirmation message than a 
                                           # real GET/POST
# The clients edit debts use case
  (r'/client/debts/list', ClientDebts),
  (r'/client/debts/add/(.*)', ClientDebtsAdd),
  (r'/client/debts/creditor/select', ClientDebtsSelectCreditor),

# The register organisation use case
  (r'/organisation/new', OrganisationNew),
  (r'/organisation/employees', OrganisationEmployeesList),
  (r'/organisation/employees/new', OrganisationEditEmployee),
  (r'/organisation/employees/edit/(.*)', OrganisationEditEmployee),
  (r'/organisation/employees/resize/(.*)', OrganisationEmployeeResize),
  (r'/organisation/zipcodes', OrganisationZipcodes), #FIXME:
  (r'/employee/photo/(.*)', Photo),

# Several employee use cases
  (r'/employee/approvals', EmployeeApprovals),
  (r'/employee/waiting', EmployeeWaiting),
  (r'/employee/approve/(.*)', EmployeeApprove),
  (r'/employee/become/(.*)', EmployeeBecome),
  (r'/employee/become', EmployeeBecome),
#  (r'/finished', Finished),
  (r'/company/new', AddCompany),
  (r'/category/new', AddCategory),
#  (r'/addemployees', AddEmployees),
  (r'/category/list', ShowCategories),
  (r'/test', Test),
  (r'/reset', ResetPassword),
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()


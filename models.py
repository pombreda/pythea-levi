from __future__ import with_statement
import os
import logging
import datetime
import pickle
import crypt
import decimal

from google.appengine.ext import db
from google.appengine.ext.db import polymodel
import wsgiref.handlers

from google.appengine.api.urlfetch import fetch
import re
import urlparse


class DecimalProperty(db.Property):
    data_type = decimal.Decimal

    def get_value_for_datastore(self, model_instance):
        value = super(DecimalProperty, self).get_value_for_datastore(model_instance)
        return str(value) if value != None else None

    def make_value_from_datastore(self, value):
        if value is None: return value
        return decimal.Decimal(value).quantize(decimal.Decimal('0.01'))

    def validate(self, value):
        value = super(DecimalProperty, self).validate(value)
        if value is None or isinstance(value, decimal.Decimal):
            return value
        elif isinstance(value, basestring):
            return decimal.Decimal(value)
        raise db.BadValueError("Property %s must be a Decimal or string." % self.name)


class User(polymodel.PolyModel):
    username = db.StringProperty()
    first_name = db.StringProperty()
    last_name= db.StringProperty()
    email = db.EmailProperty()
    password = db.ByteStringProperty()
    
    is_active = db.BooleanProperty()
    is_staff = db.BooleanProperty()
    is_superuser = db.BooleanProperty()
    
    last_login = db.DateTimeProperty()
    date_joined = db.DateTimeProperty()
    
    def set_password(self, password):
        self.password = crypt.crypt(password, os.urandom(2))

    def authenticate(self, password):
        return crypt.crypt(password, self.password) == self.password

    def start_page(self):
        return None

    
# FIXME: Organisation also needs to be scoped to 
# a zipcode. E.g. woonbron delfshaven has a different mail address
# than woonbron ijsselmonde.
lowermask = '0000AA'
uppermask = '9999ZZ'

class Organisation(polymodel.PolyModel):
    display_name = db.StringProperty()
    icon = db.LinkProperty()
    website = db.LinkProperty()
    email = db.EmailProperty()
 

class SocialWork(Organisation):
    address = db.StringProperty()
    zipCode = db.StringProperty()
    city = db.StringProperty()
    zipcodes = db.StringListProperty()
    
    def accepts(self, zipcode):
        if True:
            return True
        for zipcode in self.zipcodes:
            range = zipcode.split('-')
            lower = range[0]
            upper = lower if len(range) < 2 else range[1]
            lower = lower + lowermask[len(lower):]
            higher = higher + highermask[len(higher):]
            if lower <= zipcode <= higher:
                return True
        return False
                

class SocialWorker(User):
    organisation = db.ReferenceProperty(SocialWork, collection_name="employees")
    sysadmin = db.BooleanProperty()
    photo = db.BlobProperty()

    def set_sysadmin(self, worker, flag):
        if not self.sysadmin:
            raise Unauthorized
        else:
            worker.sysadmin = flag

    def start_page(self):
        return '/employee/handle/approvals'

class Client(User):
    address = db.StringProperty()
    zipcode = db.StringProperty()
    city = db.StringProperty()
    phone = db.PhoneNumberProperty()
    mobile = db.PhoneNumberProperty()
    state = db.StringProperty(default="NEW") # One of NEW, COMPLETED, APPROVED, DONE 
    completion_date = db.DateProperty()
    approval_date = db.DateProperty()
    archive_date = db.DateProperty() # ==> when the client is finished with entering his case file
    contact = db.ReferenceProperty(SocialWorker, collection_name="clients")


    def start_page(self):
        if self.state == 'APPROVED':
            return '/client/debts/list'
        elif self.state == 'COMPLETED':
            return '/client/register/creditors'
        elif self.state == 'FINISHED':
            return '/client/register/finished'
        else:
            return '/client/register/creditors'

    def hasCreditor(self, creditor):
        for link in self.creditors:
            if link.creditor.key().id() == creditor.key().id():
                return True

    def addCreditor(self, creditor, amount=None):
        if not self.hasCreditor(creditor):
            link = CreditorLink(creditor=creditor, user=self, estimated_amount=amount)
            link.put()
    
    def removeCreditor(self, creditor):
        for link in self.creditors:
            if link.creditor.key().id() == creditor.key().id():
                link.delete()

    def complete(self):
        self.state = "COMPLETED"
        self.put()

    def approve(self):
        self.state = "APPROVED"
        self.put()

    def finish(self):
        self.state = "FINISHED"
        self.put()

    def reopen(self):
        self.state = "APPROVED" 
        self.put()

class Category(db.Model):
    label = db.StringProperty()

    def __str__(self):
        return self.label

icon_re = re.compile(r'<link\s+rel=".*?icon"\s+href="(.*?)"', re.M | re.I)
base_re = re.compile(r'<base\s+href="(.*?)"', re.M | re.I)
keywords_re = re.compile(r'<meta\s+name="keywords"\s+content=["\'](.*?)["\']')

class Creditor(Organisation):
    tags = db.StringListProperty()
    is_collector = db.BooleanProperty(default=False)

    def expand(self):
        url = self.website
        homepage = fetch(url)
        base = base_re.search(homepage.content)
        if base:
            base = base.group(1)
        elif homepage.final_url:
            if homepage.final_url.startswith('/'):
                base = url + homepage.final_url
            else:
                base = homepage.final_url
        else:
            base = url
        icon = icon_re.search(homepage.content)
        icon = icon.group(1) if icon else '/favicon.ico'
        icon_url = urlparse.urljoin(base, icon)
        keywords = keywords_re.search(homepage.content)
        keywords = keywords.group(1) if keywords else ""
        keywords = keywords.decode('utf-8')
        keywords = keywords.split(',')
        self.tags = keywords
        self.icon = icon_url
        if not self.email:
            hostname = urlparse.urlparse(url).hostname
            if hostname.startswith('www'):
                hostname = '.'.join(hostname.split('.')[1:])
            self.email = 'info@' + hostname
        if not self.display_name:
            hostname = urlparse.urlparse(url).hostname
            name = hostname.split('.')[-2]
            self.display_name = name

class CreditorLink(db.Model):
    creditor = db.ReferenceProperty(Creditor)
    user = db.ReferenceProperty(Client, collection_name='creditors')
    estimated_amount = DecimalProperty(default=decimal.Decimal('0.00')) 
    approved = db.BooleanProperty()
    last_email_date = db.DateProperty()
    complete = db.BooleanProperty()
    registration_date = db.DateProperty(auto_now_add=True)
    last_changed_date = db.DateProperty(auto_now=True)

    def send_email(self):
        logging.error("FIXME: need to actually send an email")
        self.last_email_date = datetime.date.today()
        self.approve()

    def approve(self):
        self.approved = True

    def status(self):
        if not self.approved:
            return "WAITING FOR APPROVAL"
        elif not self.last_email_date:
            return "NO EMAIL SENT"
        elif not self.debts:
            return "WAITING FOR ANSWER"
        elif not self.complete:
            return "WAITING FOR 2ND APPROVAL"
        elif self.complete:
            return "COMPLETE"
        else:
            return "ILLEGAL STATE"


class Debt(db.Model):
    creditor = db.ReferenceProperty(CreditorLink, collection_name='debts')
    collector = db.ReferenceProperty(Creditor)
    original_date = db.DateProperty()
    creditor_dossier_number = db.StringProperty()
    collector_dossier_number = db.StringProperty()
    registration_date = db.DateProperty(auto_now_add=True)
    last_changed_date = db.DateProperty(auto_now=True)
    amount = DecimalProperty(default=decimal.Decimal('0.00')) 
    payment_amount = DecimalProperty(default=decimal.Decimal('0.00')) 


class Annotation(db.Model):
    subject = db.ReferenceProperty(db.Model, collection_name='annotation')
    ag = db.CategoryProperty()
    entry_date = db.DateProperty(auto_now_add=True)
    date = db.DateProperty()
    text = db.TextProperty()


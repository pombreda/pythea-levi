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
import time

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

def encode_b36(number):
    if not isinstance(number, (int, long)):
        raise TypeError('number must be an integer')
    if number < 0:
        raise ValueError('number must be positive')

    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

    base36 = ''
    while number:
        number, i = divmod(number, 36)
        base36 = alphabet[i] + base36

    return base36 or alphabet[0]

def decode_b36(number):
    return int(number,36)

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
        if(crypt.crypt(password, self.password) == self.password):
            self.last_login = datetime.datetime.now()
            self.put()
            return True
        else:
            return False

    def start_page(self):
        return None

    def make_token(self):
        """
        Returns a token that can be used once to do a password reset
        for the given user.
        """
        return self._make_token_with_timestamp(self._now())

    def check_token(self, token):
        """Verify a password reset token"""
        try:
            ts_b36, hash = token.split("-")
        except ValueError:
            return False

        try:
            ts = decode_b36(ts_b36)
        except ValueError:
            return False

        # Check that the timestamp/uid has not been tampered with
        if self._make_token_with_timestamp(ts) != token:
            return False

        # Check the timestamp is not older than a day
        if self._now() - ts > 1:
            return False
        return True

 
    def _now(self):
        return int(time.time() / 1000)

    def _make_token_with_timestamp(self, timestamp):
        import hashlib
        ts_b36 = encode_b36(timestamp)
        key_salt = self.password
        login_timestamp = self.last_login.isoformat()
        value = str(self.username) + self.password + login_timestamp + ts_b36
        hash = hashlib.sha1(value).hexdigest()[:6].upper()
        return '%s-%s' % (ts_b36, hash)

    
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
    original_photo = db.BlobProperty()

    def set_sysadmin(self, worker, flag):
        if not self.sysadmin:
            raise Unauthorized
        else:
            worker.sysadmin = flag

    def start_page(self):
        return '/employee/cases/list'

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
                return link
        return False

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
    question = db.StringProperty()
    new_question = db.StringProperty()
    description = db.StringProperty()
    long_desc = db.TextProperty()

    def __str__(self):
        return self.label

icon_re = re.compile(r'<link\s+(?:type=".*?"\s+)?rel=".*?icon?"\s+href="(.*?)"', re.M | re.I)
base_re = re.compile(r'<base\s+href="(.*?)"', re.M | re.I)
keywords_re = re.compile(r'<meta\s+name="keywords"\s+content=["\'](.*?)["\']')

class Creditor(Organisation):
    tags = db.StringListProperty()
    categories = db.StringListProperty()
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
        elif not self.debts.count():
            return "WAITING FOR ANSWER"
        elif self.complete:
            return "COMPLETE"
        else:
            return "ILLEGAL STATE"

    def status(self):
        #if not self.approved:
        #    return "WAITING FOR APPROVAL"
        count = 0
        for debt in self.debts:
            logging.error("debt %d" % (count))
            if debt.collector: 
                logging.error("debt collected by %s" % debt.collector.display_name)
                collector = self.user.hasCreditor(debt.collector)
                if not collector:
                    logging.error("\t but this collector is not linked to the customer")
                    return "IN COLLECTION: MISMATCH: ERROR collector not found"
                else:
                    logging.error("\t trying to find matching debts")
                    count2 = 0
                    for debt2 in collector.debts:
                        count2 = count2 + 1
                        logging.error("\t debt2 %s" % debt2 )
                        try: 
                             if debt2.collected_for and debt2.collected_for.key().id() == debt.creditor.creditor.key().id():
                                  logging.error("match")
                                  return "IN COLLECTION: COMPLETE"
                             else:
                                  logging.error("no match")
                        except Exception, e:
                             logging.error("An error occurred matching %s", e)
                    logging.error("We have left the loop count is now %d" % count2)
                    if count2:
                        return "IN COLLECTION: MISMATCH: ERROR collector has no collections for this creditor"
                    if not count2:
                        return "IN COLLECTION: WAITING FOR COLLECTOR"
            else:
                logging.error("self collected debt")
                count = count + 1
        else:
            if count:
                logging.error("only self collected debts")
                return "COMPLETE"
            else:
                logging.error("no debts for this creditor")
                return "WAITING FOR ANSWER"
        return "ERROR: UNKNOWN STATE"


class Debt(db.Model):
    creditor = db.ReferenceProperty(CreditorLink, collection_name='debts')
    collector = db.ReferenceProperty(Creditor, collection_name="debts")
    collected_for = db.ReferenceProperty(Creditor, collection_name="collections")

    original_date = db.DateProperty()
    creditor_dossier_number = db.StringProperty()
    collector_dossier_number = db.StringProperty()
    registration_date = db.DateProperty(auto_now_add=True)
    last_changed_date = db.DateProperty(auto_now=True)
    amount = DecimalProperty(default=decimal.Decimal('0.00')) 
    payment_amount = DecimalProperty(default=decimal.Decimal('0.00')) 


class Annotation(db.Model):
    subject = db.ReferenceProperty(db.Model, collection_name='annotations')
    author = db.ReferenceProperty(User)
    admin = db.StringProperty()
    ag = db.CategoryProperty()
    entry_date = db.DateProperty(auto_now_add=True)
    date = db.DateProperty()
    text = db.TextProperty()

class Screen(db.Model):
    description = db.StringProperty()
    design = db.BlobProperty()

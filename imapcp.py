#!/usr/bin/env python
#-*- coding: utf8 -*-

__program__ = "IMAP4 mailbox copy tool"
__author__ = "s0rg"
__version__ = "0.7"

import sys
import re
import ssl
import imaplib
from time import time
from email import message_from_string
from email.utils import parsedate
from getpass import getpass
from urlparse import urlsplit


try:
    from argparse import ArgumentParser

    def parse_args(args):
        parser = ArgumentParser(description=__program__)
        parser.add_argument('-v', '--version', action='version', version=__version__)
        parser.add_argument('--move', action='store_true', dest='do_move', help='perform "move" (clear source) instead of copy', default=False)
        parser.add_argument('--box', action='store', dest='mailbox', help='copy/move only this mailbox (default - all)', default=None)
        parser.add_argument('--ssl', action='store_true', dest='is_ssl', help='copy/move only this mailbox (default - all)', default=False)
        parser.add_argument('uri_source', action='store', help='Source ( user[:password@localhost:143] )')
        parser.add_argument('uri_dest', action='store', help='Destination ( user[:password@localhost:143] )')
        return parser.parse_args(args)

except ImportError, _:
    from optparse import OptionParser

    class OptHack(object):
        def __init__(self, **kwargs):
            for k, w in kwargs.iteritems():
                self.__setattr__(k, w)

    def parse_args(args):
        parser = OptionParser()
        parser.add_option('--move', action='store_true', dest='do_move', default=False)
        parser.add_option('--box', action='store', dest='mailbox', default=None)
        parser.add_option('--ssl', action='store_true', dest='is_ssl', default=False)

        opts, rem = parser.parse_args(args)
        if len(rem) != 2:
            print 'Bad Command Line!'
            sys.exit(1)

        return OptHack(do_move=opts.do_move, mailbox=opts.mailbox, uri_source=rem[0], uri_dest=rem[1], is_ssl=opts.is_ssl)


'''
Code for parse_list_response taken here:
http://www.doughellmann.com/PyMOTW/imaplib/index.html
'''
IMAP_LIST_RESPONSE_RE = re.compile(r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)')

def parse_list_response(line):
    flags, delimiter, mailbox_name = IMAP_LIST_RESPONSE_RE.match(line).groups()
    mailbox_name = mailbox_name.strip('"')
    return (flags, delimiter, mailbox_name)


class ImapBox(object):
    def __init__(self, login, password, host, port, ssl=False):
        self._mailboxes = {}
        self._login = login
        self._password = password
        self._host = host
        self._port = port
        self._is_ssl = ssl

    def connect(self):
        if self._is_ssl:
            self._conn = imaplib.IMAP4_SSL(self._host, self._port)
            self._conn.ssl().ssl_version = ssl.PROTOCOL_SSLv3
        else:
            self._conn = imaplib.IMAP4(self._host, self._port)

        self._conn.login(self._login, self._password)

        typ, res = self._conn.list()
        if typ != 'OK':
            raise Exception('IMAP "list" command failed!')

        for ln in res:
            flags, delimiter, mailbox_name = parse_list_response(ln)
            self._conn.select(mailbox_name, readonly=True)
            typ, [msg_ids] = self._conn.search(None, 'ALL')
            if typ == 'OK':
                self._mailboxes[mailbox_name] = msg_ids.split()

        return self

    def get_boxes(self):
        return self._mailboxes.keys()

    def get_message(self, mailbox, msg_id=None):
        if msg_id is None:
            return self._mailboxes.get(mailbox, [])

        if mailbox not in self._mailboxes:
            return None

        typ, result = self._conn.select(mailbox, readonly=True)
        if typ != 'OK':
            return None

        typ, result = self._conn.fetch(msg_id, '(RFC822)')
        if typ != 'OK':
            return None

        for response_part in result:
            if isinstance(response_part, tuple):
                return message_from_string(response_part[1])
        else:
            return None

    def copy(self, to, mbox_name=None, do_move=False):
        if mbox_name is not None:
            self._copy_box(to, mbox_name, do_move)
        else:
            for mb in self._mailboxes.iterkeys():
                self._copy_box(to, mb, do_move)

    def _copy_box(self, to, mbox, move):
        msgs = self.get_message(mbox)
        for msg in msgs:
            mail = self.get_message(mbox, msg)
            if mail is not None:
                to.add_message(mbox, mail)

        if move:
            self._conn.store(','.join(msgs), '+FLAGS', r'(\Deleted)')
            self._conn.expunge()

        print '{} messages {} from {}'.format(len(msgs), 'moved' if move else 'copied' , mbox)

    def add_message(self, mailbox, msg):
        if mailbox not in self._mailboxes:
            self._conn.create(mailbox)

        date = time()
        if 'date' in msg:
            d = parsedate(msg['date'])
            if d is not None:
                date = d
        try:
            date = imaplib.Time2Internaldate(date)
        except ValueError:
            date = imaplib.Time2Internaldate(time())

        self._conn.append(mailbox, '', date, str(msg))

    def close(self):
        self._conn.close()
        self._conn.logout()


def imap_connect(uri_str, is_ssl=False):
    if not uri_str.startswith('imap://'):
        uri = urlsplit('//' + uri_str, scheme='imap')
    else:
        uri = urlsplit(uri_str)

    if uri.username is None:
        print '[-] No username found in %s!' % uri_str
        return None

    password = uri.password if uri.password is not None \
                            else getpass(prompt='password for %s: ' % uri.username)

    host = uri.hostname or 'localhost'
    port = uri.port or imaplib.IMAP4_PORT

    #For Debug
    #print 'User: {} Password: {} Host: {} Port: {}'.format(uri.username, password, host, port)

    return ImapBox(uri.username, password, host, port, is_ssl).connect()


def main(args):
    opt = parse_args(args[1:])

    src = imap_connect(opt.uri_source, opt.is_ssl)
    dst = imap_connect(opt.uri_dest, opt.is_ssl)

    if None in (src, dst):
        return 1

    src.copy(dst, opt.mailbox, opt.do_move)

    src.close()
    dst.close()

    return 0


##### entry point ######
sys.exit(main(sys.argv))
########################

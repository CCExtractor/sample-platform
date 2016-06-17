#!/usr/bin/python

import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

if len(sys.argv) != 5:
    print('Invalid number of arguments. Expected 5 arguments, got %s' %
          len(sys.argv))
    exit()


def run():
    from database import create_session
    from mod_auth.models import User, Role
    from mod_auth.models import Page

    db = create_session(sys.argv[1])
    # Create pages if not existing
    pages = Page.query.all()
    if len(pages) == 0:
        page_entries = {
            'report.dashboard': 'Dashboard',
            'config.notifications': 'Notification services',
            'config.data_processing': 'Data processing',
            'config.services': 'Honeypot services',
            'auth.users': 'User manager',
            'auth.access': 'Access manager',
            'honeypot.profiles': 'Profile management',
            'honeypot.manage': 'Honeypot management'
        }
        for name, pretty_name in page_entries.iteritems():
            page = Page(name, pretty_name)
            db.add(page)
            db.commit()
        # Add support pages
        db.add(Page('support.about', 'About', True))
        db.add(Page('support.support', 'Support', True))
        db.commit()
    # Create admin role, or check if it already exists
    existing = Role.query.filter(Role.is_admin).first()
    if existing is None:
        role = Role("Admin")
        db.add(role)
        db.commit()
        existing = role
    else:
        # Check if there's at least one admin user
        admin = User.query.filter(User.role_id == existing.id).first()
        if admin is not None:
            print("Admin already exists: %s" % admin.name)
            return

    user = User(existing.id, sys.argv[2], sys.argv[3],
                User.generate_hash(sys.argv[4]))
    db.add(user)
    db.commit()
    print("Admin user created with name: %s" % user.name)

run()

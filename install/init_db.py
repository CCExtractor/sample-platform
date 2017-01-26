#!/usr/bin/python

import sys
from os import path

# Need to append server root path to ensure we can import the necessary files.
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

if len(sys.argv) != 6:
    print('Invalid number of arguments. Expected 5 arguments, got %s' %
          len(sys.argv))
    exit()


def run():
    from database import create_session
    from mod_auth.models import User, Role

    db = create_session(sys.argv[1])
    # Check if there's at least one admin user
    admin = User.query.filter(User.role == Role.admin).first()
    if admin is not None:
        print("Admin already exists: %s" % admin.name)
        return

    user = User(sys.argv[2], Role.admin, sys.argv[3],
                User.generate_hash(sys.argv[4]))
    db.add(user)

    #create sample database
    print(sys.arg[5])
    if sys.arg[5] == "y":
        from mod_home.models import CCExtractorVersion, GeneralData
        from mod_regression.models import Category, RegressionTest, regressionTestCategoryLinkTable
        from mod_sample.models import Sample
        from mod_sample.media_info_parser import MediaInfoFetcher
        try:
            category = Category('Broken','Samples that are broken')
            db.add(category)

            category = Category('DVB','Samples that contain DVB subtitles')
            db.add(category)

            category = Category('DVD','Samples that contain DVD subtitles')
            db.add(category)

            category = Category('MP4','Samples that are stored in the MP4 format')
            db.add(category)

            category = Category('General','General regression samples')
            db.add(category)


            sample = Sample('9a496d38281a9499c89b2212a66d0ee40b7778858de549c76232ac54a62aa1d9','mpg','sample1')
            db.add(sample)

            sample = Sample('56c9f345482c635f20340d13001f1083a7c1913c787075d6055c112fe8e2fcaa','mpg','sample2')
            db.add(sample)


            cc_version = CCExtractorVersion('0.84','2016-12-16','77da2dc873cc25dbf606a3b04172aa9fb1370f32')
            db.add(cc_version)


            reg_test = RegressionTest('1','-autoprogram -out=ttxt -latin1','file','file',10)
            db.add(reg_test)

            reg_test = RegressionTest('2','-autoprogram -out=ttxt -latin1 -ucla','file','file',10)
            db.add(reg_test)


            reg_test_category = Table(
                'regression_test_category', Base.metadata,
                Column(1),
                Column(5))

            db.add(reg_test_category)

            reg_test_category = Table(
                'regression_test_category', Base.metadata,
                Column(2),
                Column(5))

            db.add(reg_test_category)

            gen_data = GeneralData('last_commit','71dffd6eb30c1f4b5cf800307de845072ce33262')
            db.add(gen_data)
        except Exception as err:
            print(str(err))


    db.commit()
    print("Admin user created with name: %s" % user.name)

run()

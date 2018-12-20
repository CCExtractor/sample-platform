from run import app
from database import Base
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand

from mod_home.models import GeneralData, CCExtractorVersion
from mod_sample.models import Issue, Sample, ExtraFile, ForbiddenExtension, ForbiddenMimeType
from mod_regression.models import Category, RegressionTestOutput, RegressionTest, regressionTestLinkTable, InputType, OutputType
from mod_auth.models import Role, User
from mod_home.models import CCExtractorVersion
from mod_test.models import TestType, Test, TestStatus, TestProgress, Fork, TestPlatform, TestResultFile, TestResult
from mod_upload.models import Platform, Upload, QueuedSample, UploadLog, FTPActive, FTPCredentials
from mod_customized.models import CustomizedTest, TestFork
from mod_ci.models import BlockedUsers, Kvm, MaintenanceMode

app.config['SQLALCHEMY_DATABASE_URI'] = app.config['DATABASE_URI']
migrate = Migrate(app, Base)
manager = Manager(app)
manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()

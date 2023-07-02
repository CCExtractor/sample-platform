# CCExtractor Sample Platform

[![Run tests and code checks](https://github.com/CCExtractor/sample-platform/workflows/Run%20tests%20and%20code%20checks/badge.svg)](https://github.com/CCExtractor/sample-platform/actions?query=workflow%3A%22Run+tests+and+code+checks%22) [![codecov](https://codecov.io/gh/CCExtractor/sample-platform/branch/master/graph/badge.svg)](https://codecov.io/gh/CCExtractor/sample-platform)

This repository contains the code for a platform that manages a test suite bot, sample upload and more. This platform allows for a unified place to
report errors, submit samples, view existing samples and more. It was
originally developed during GSoC 2015 and rewritten during the 2016 edition. It was further improved and worked upon during GSoC 2017, 2018, 2019 and 2022.

To see the live version of the platform, simply go to
[CCExtractor Submission Platform](https://sampleplatform.ccextractor.org/).

## Concept

While CCExtractor is an awesome tool and it works flawlessly most of the time,
bugs occur occasionally (as with all existing software). These are usually
reported through a variety of channels (private email, mailing list, GitHub,
and so on...).

The aim of this project is to build a platform, which is accessible to
everyone ([after signing up](https://sampleplatform.ccextractor.org/account/signup)), that provides a single place to upload, view 
samples and associated test results.

## Installation

An installation guideline can be found here:
[installation guide](install/installation.md).

## Sample Updates

A lot of times it may happen that we add new features to ccextractor which render the result files associated with
regression tests useless. In these cases, the tests can give false negative. For such cases, we should update the existing
result files by the following command.

```shell
python manage.py update /path/to/ccextractor/executable
```

NOTE: Please backup old results and be sure about updating them as there is no method to go back.

## Database Migrations

Sample-Platform uses flask-migrate to handle database migrations.

If you want to perform more complex actions than the ones mentioned below, please have a look at the [flask-migrate 
command reference](https://flask-migrate.readthedocs.io/en/latest/#command-reference).

**NOTE: For the below commands to function properly, `FLASK_APP=/path/to/run.py` should be set in the environment variables.**

#### First Time With Flask-Migrate

If this is the first time that flask-migrate is being installed or run alongside existing database, use the 
following command to create a head stamp in your database:

```bash
flask db stamp head
```

#### Applying Schema Update On Existing Database

It is recommeneded to perform Database upgrades, whenever database schema is updated, using the below commands:

```bash
flask db upgrade
```

#### Removing Last Schema Update On Existing Database

Remove the last database update using the below commands:

```bash
flask db downgrade
```

#### Updating Schema

Whenever a database model's schema is update, run the following command to generate migrations for it.

```bash
flask db migrate
```

## Contributing

All information with regards to contributing can be found here:
[contributors guide](.github/CONTRIBUTING.md).

## Testing

Sample-platform is regularly tested via Travis CI.

We use `nosetests` to manage testing and it can be run locally as follows:

For creating a virtual environment, we use [virtualenv](https://pypi.org/project/virtualenv/).

```bash
virtualenv venv                          # create a virtual environment
source venv/bin/activate                 # activate the virtual environment
pip install -r requirements.txt          # install dependencies
pip install -r test-requirements.txt     # install test dependencies
TESTING=True nose2
```

## Migrating platform between machines

In case you want to replicate/migrate a platform instance with all the data, samples, regression tests.etc., follow the following steps:
- Install platform on the new instance, using the [installation guide](install/installation.md).
- Now transfer the contents of the previous GCS bucket to the new GCS bucket and export the SQL database of the previous platform instance into a file using the following command:
    ```
    mysqldump -u PLATFORM_USER_USERNAME -p PLATFORM_DATABASE_NAME > sample_platform.sql
    ```
    PLATFORM_USER_USERNAME and PLATFORM_DATABASE_NAME values are details for the SQL database of the previous platform instance.
- Now import the database using the `sample_platform.sql` file into the new instance using the following command:
    ```
    mysql -u NEW_PLATFORM_USER_USERNAME -p NEW_PLATFORM_DATABASE_NAME < sample_platform.sql
    ```
    NEW_PLATFORM_USER_USERNAME and NEW_PLATFORM_DATABASE_NAME values are details for the SQL database of the new platform instance.

## Etiquettes

We follow certain etiquettes which include docstrings, annotation, import sorting etc.

### DocStrings Testing

Sample-platform uses docstrings heavily to document modules and methods.

We use `pydocstyle` to oversee the docstring format and etiquettes. Please run the following to check if you've
followed the style before sending a PR.

```bash
pydocstyle ./           # check all .py files with pydocstyle
```

### Imports

We use `isort` to introduce a style on how imports should be made.

Please check your imports before making a commit using the following commands.

```bash
isort . --diff      # see proposed changes without applying them
isort . --atomic    # apply changes to import order without breaking syntax
```

### Generate Typing And Annotations

We use `MonkeyType` or `PyType` to generate typing for our code. It is a simple tool that [semi] automates the
process of generating annotations using runtime trace.

To generate typing for your code, follow the below procedure.

#### Using MonkeyType

This method uses runtime trace information to generate typing and is **highly recommended** over using `PyType`.

NOTE: You **must have written unit-tests for the new code** in order to add annotations using MonkeyType.

```bash
monkeytype run `TESTING=True nosetests path/to/new.py/file:ClassName`     # classname where new tests added
monkeytype apply module.name                                               # apply the suggested changes
```

#### Using PyType

This method uses the knowledge of how the code is used to figure out the types.

NOTE: Only use this method only if `MonkeyType` method fails for the file.

```bash
pytype path/to/.py/file                    # path to the new code's file
merge-pyi -i path/to/.py/file .pytype/pyi/path/to/.pyi/file     # apply the suggested changes
```

Once you've generated the annotations using the above tools, follow the below procedure.

```bash
isort --atmoic /path/to/new.py/file                                        # sort the imports
mypy /path/to/new.py/file                                                  # fix the errors reported by mypy
git diff /path/to/new.py/file                                              # manually check the file for missing typings
pycodestyle ./ --config=./.pycodestylerc                                   # to check for PEP8 violations
```

NOTE: Manual inspection is very important. If then you feel that a mypy error is inappropriate or overkill, append
`# type: ignore` at the end of the line.

Only once the above procedure is finished for all new files, one should commit the changes.

References to know more:

- To know about static typing: https://realpython.com/python-type-checking/#annotations
- To know about MonkeyType: https://instagram-engineering.com/let-your-code-type-hint-itself-introducing-open-source-monkeytype-a855c7284881
- To know about PyType: https://github.com/google/pytype
- MyPy Cheatsheet for TypeHints: https://mypy.readthedocs.io/en/latest/cheat_sheet_py3.html

### Static Typing Test

We use `mypy` to introduce a static typing.

Please check your code for static typing violations using the following commands.

```bash
mypy .
```

## Security

Even though many precautions have been taken to ensure that this software is
stable and secure, bugs can occur. In case there is a security related issue,
please send an email to ccextractor@canihavesome.coffee (GPG key
[0xF8643F5B](http://pgp.mit.edu/pks/lookup?op=vindex&search=0x3AFDC9BFF8643F5B),
fingerprint 53FF DE55 6DFC 27C3 C688 1A49 3AFD C9BF F864 3F5B) instead of
using the issue tracker. This will help to prevent abuse while the issue is
being resolved.

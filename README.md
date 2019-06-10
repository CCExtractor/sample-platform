# CCExtractor Sample Platform

[![Build Status](https://travis-ci.org/CCExtractor/sample-platform.svg?branch=master)](https://travis-ci.org/CCExtractor/sample-platform) [![codecov](https://codecov.io/gh/CCExtractor/sample-platform/branch/master/graph/badge.svg)](https://codecov.io/gh/CCExtractor/sample-platform)

This repository contains the code for a platform that manages a test suite bot, sample upload and more. This platform allows for a unified place to
report errors, submit samples, view existing samples and more. It was
originally developed during GSoC 2015 and rewritten during GSoC 2016. It was further improved and worked upon during GSoC 2017 and GSoC 2018.

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

## Contributing

All information with regards to contributing can be found here:
[contributors guide](.github/CONTRIBUTING.md).

## Testing

Sample-platform is regularly tested via Travis CI.

We use `nosetests` to manage testing and it can be run locally as follows:

```bash
pipenv shell --three        # make virtual environment
pipenv install --dev        # install development dependencies
TESTING=True pipenv run nosetests --with-cov --cov-config .coveragerc
```

## Etiquettes

We follow certain etiquettes which include docstrings, annotation, import sorting etc.

### Setup

The operations listed below are only for developers. The tools used below can be installed at once as,

```bash
pipenv shell --three    # if not inside pipenv shell already
pipenv install --dev    # if first time running dev-dependencies
```

If you are adding a new module which will be required just by developers, use below commands.

```bash
pipenv install --dev [MODULE_NAME]
```

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
isort --rc --diff .     # see proposed changes without applying them
isort -rc --atomic .    # apply changes to import order without breaking syntax
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
isort -rc --atmoic /path/to/new.py/file                                    # sort the imports
mypy /path/to/new.py/file                                                  # fix the errors reported by mypy
git diff /path/to/new.py/file                                              # manually check the file for missing typings
pycodestyle ./ --config=./.pycodestylerc                                   # to check for PEP8 violations
```

NOTE: Manual inspection is very important.

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
mypy mod_*
```

## Security

Even though many precautions have been taken to ensure that this software is
stable and secure, bugs can occur. In case there is a security related issue,
please send an email to ccextractor@canihavesome.coffee (GPG key
[0xF8643F5B](http://pgp.mit.edu/pks/lookup?op=vindex&search=0x3AFDC9BFF8643F5B),
fingerprint 53FF DE55 6DFC 27C3 C688 1A49 3AFD C9BF F864 3F5B) instead of
using the issue tracker. This will help to prevent abuse while the issue is
being resolved.

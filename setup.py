#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License

import ast
import os
import re
import sys

from setuptools import find_packages, setup


assert sys.version_info >= (3, 7, 0), "later requires Python >=3.7"
THISDIR = os.path.abspath(os.path.dirname(__file__))


def long_desc() -> str:
    with open(os.path.join(THISDIR, "README.rst"), "r") as f:
        return f.read()


def version() -> str:
    _version_re = re.compile(r"__version__\s+=\s+(?P<version>.*)")

    with open(os.path.join(THISDIR, "later", "__init__.py"), "r") as f:
        version = _version_re.search(f.read()).group("version")
        return str(ast.literal_eval(version))


setup(
    name="later",
    version=version(),
    license="Apache 2.0",
    url="https://github.com/facebookincubator/later",
    description="A toolbox for asyncio services",
    long_description=long_desc(),
    keywords=["asyncio", "later"],
    author="Jason Fried, Facebook",
    author_email="fried@fb.com",
    zip_safe=True,
    packages=find_packages(include=["later.*", "later"]),
    python_requires=">3.7",
    test_suite="later.tests.base",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Framework :: AsyncIO",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX",
        "Operating System :: MacOS :: MacOS X",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Testing",
    ],
    install_requires=["async-timeout >=2.0.0,<5.0.0"],
    # Per PEP 561
    package_data={"later": ["py.typed"]},
    include_package_data=True,
)

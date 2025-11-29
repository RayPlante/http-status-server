from setuptools import setup, find_packages
from unittest import TestLoader

pkgname = 'http_status_server'

def discover_tests():
    return TestLoader().discover('tests', pattern='test_*.py')

setup(
    packages=find_packages(
        include=[pkgname]
    ),
    test_suite='setup.discover_tests'
)

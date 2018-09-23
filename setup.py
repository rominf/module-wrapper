# -*- coding: utf-8 -*-
from distutils.core import setup

packages = \
['module_wrapper']

package_data = \
{'': ['*']}

setup_kwargs = {
    'name': 'module-wrapper',
    'version': '0.1.0',
    'description': 'Module wrapper Python library',
    'long_description': '# module-wrapper\nModule wrapper Python library\n',
    'author': 'Roman Inflianskas',
    'author_email': 'infroma@gmail.com',
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'python_requires': '>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',
}


setup(**setup_kwargs)

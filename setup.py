# -*- coding: utf-8 -*-
from distutils.core import setup

packages = \
['module_wrapper']

package_data = \
{'': ['*']}

install_requires = \
['wrapt']

setup_kwargs = {
    'name': 'module-wrapper',
    'version': '0.1.9',
    'description': 'Module wrapper Python library',
    'long_description': "# module-wrapper - module wrapper Python library\n[![License](https://img.shields.io/pypi/l/module-wrapper.svg)](https://www.apache.org/licenses/LICENSE-2.0)\n![PyPI - Python Version](https://img.shields.io/pypi/pyversions/module-wrapper.svg)\n[![PyPI](https://img.shields.io/pypi/v/module-wrapper.svg)](https://pypi.org/project/module-wrapper/)\n[![Documentation Status](https://img.shields.io/readthedocs/module-wrapper.svg)](http://module-wrapper.readthedocs.io/en/latest/)\n \n`module-wrapper` contains `wrap` function, which is used to wrap module, class, function or another variable \nrecursively.\n\n## Installation\nTo install from [PyPI](https://pypi.org/project/module-wrapper/) run:\n```shell\n$ pip install module-wrapper\n```\n\n## Usage\nExample from [aioify](https://github.com/yifeikong/aioify):\n```pyhton\nfrom functools import wraps, partial\nimport asyncio\n\nimport module_wrapper\n\n\n__all__ = ['aioify']\n\n\ndef wrap(func):\n    @wraps(func)\n    async def run(*args, loop=None, executor=None, **kwargs):\n        if loop is None:\n            loop = asyncio.get_event_loop()\n        pfunc = partial(func, *args, **kwargs)\n        return await loop.run_in_executor(executor, pfunc)\n    return run\n\n\ndef aioify(obj, name=None):\n    def create(cls):\n        return 'create', wrap(cls)\n\n    return module_wrapper.wrap(obj=obj, wrapper=wrap, methods_to_add={create}, name=name)\n```\n",
    'author': 'Roman Inflianskas',
    'author_email': 'infroma@gmail.com',
    'url': 'https://github.com/rominf/module-wrapper',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',
}


setup(**setup_kwargs)

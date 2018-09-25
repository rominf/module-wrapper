# module-wrapper - module wrapper Python library
[![License](https://img.shields.io/pypi/l/module-wrapper.svg)](https://www.apache.org/licenses/LICENSE-2.0)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/module-wrapper.svg)
[![PyPI](https://img.shields.io/pypi/v/module-wrapper.svg)](https://pypi.org/project/module-wrapper/)
[![Documentation Status](https://img.shields.io/readthedocs/module-wrapper.svg)](http://module-wrapper.readthedocs.io/en/latest/)
 
`module-wrapper` contains `wrap` function, which is used to wrap module, class, function or another variable 
recursively.

## Installation
To install from [PyPI](https://pypi.org/project/module-wrapper/) run:
```shell
$ pip install module-wrapper
```

## Usage
Example from [aioify](https://github.com/yifeikong/aioify):
```pyhton
from functools import wraps, partial
import asyncio

import module_wrapper


__all__ = ['aioify']


def wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)
    return run


def aioify(obj, name=None):
    def create(cls):
        return 'create', wrap(cls)

    return module_wrapper.wrap(obj=obj, wrapper=wrap, methods_to_add={create}, name=name)
```
